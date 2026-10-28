"""Post proof of work (screenshots and short clips) to an Azure DevOps ticket.

    python ticket_proof.py doctor                               # setup, sign-in and board access
    python ticket_proof.py tickets [--sprint "Sprint 3"]        # the current sprint's tickets, yours flagged
    python ticket_proof.py lookup  --ticket 123                 # title, state, description, comments
    python ticket_proof.py attach  --ticket 123 --file a.png clip.mp4 --caption "..." "..."
    python ticket_proof.py status  --ticket 123                 # what is waiting to post (no network)
    python ticket_proof.py remove  --ticket 123 --file <name>   # drop one waiting capture
    python ticket_proof.py post    --ticket 123 --note "..." [--body summary.html] [--preview] [--done]

Which board: the project's `.claude/ticket-board.json` (see the skill's README), else the Azure DevOps project of
the repository's `origin` remote. Sign-in: the Azure CLI (`az login`); no token is ever stored.

Captures wait in <capturesFolder>/<ticket>/ (default Artifacts/TicketProof) with a manifest.json, until `post` sends
them as one comment: images inline, clips as links, every file also on the ticket's Attachments tab. Tickets from
990000 up are scratch: anything may be filed there for a test, and nothing posts from them.
"""

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

MARKER = "Ticket proof · after"
ADO_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"
API = "7.1"
COMMENTS_API = "7.1-preview.4"
CONFIG_NAME = os.path.join(".claude", "ticket-board.json")
FINISHED_STATES = {"Done", "Closed", "Resolved", "Removed"}
FIRST_SCRATCH_TICKET = 990000
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
VIDEO_TYPES = {".mp4", ".mov", ".webm", ".m4v"}
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
WORK_ITEM_FIELDS = ["System.Title", "System.State", "System.WorkItemType", "System.IterationPath",
                    "System.AssignedTo", "System.AreaPath"]
REMOTE_RE = re.compile(r"https://(?:[^@/]+@)?dev\.azure\.com/([^/]+)/([^/]+)/_git/[^/]+?/?$")
VS_REMOTE_RE = re.compile(r"https://(?:[^@/]+@)?([^./]+)\.visualstudio\.com/([^/]+)/_git/[^/]+?/?$")


def fail(message, detail=""):
    """Exit with a first line a person can act on; the detail follows."""
    sys.exit(f"{message}\n{detail}".rstrip())


# --- where things are ----------------------------------------------------------

def git(*args, cwd=None):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip() if proc.returncode == 0 else ""


def project_root(start=None):
    """The folder holding .claude/ticket-board.json, searched from the working directory up to the repository
    root; else the repository root; else the working directory."""
    here = pathlib.Path(start or os.getcwd()).resolve()
    top = git("rev-parse", "--show-toplevel", cwd=here)
    stop = pathlib.Path(top).resolve() if top else None
    for folder in [here, *here.parents]:
        if (folder / CONFIG_NAME).is_file():
            return folder
        if stop is not None and folder == stop:
            break
    return stop or here


def board_from_remote(url):
    """(organization URL, project) from an Azure DevOps git remote, or None."""
    m = REMOTE_RE.match(url or "")
    if m:
        return f"https://dev.azure.com/{urllib.parse.unquote(m.group(1))}", urllib.parse.unquote(m.group(2))
    m = VS_REMOTE_RE.match(url or "")
    if m:
        return f"https://dev.azure.com/{urllib.parse.unquote(m.group(1))}", urllib.parse.unquote(m.group(2))
    return None


def normalise_organization(value):
    value = value.strip().rstrip("/")
    return value if value.startswith("https://") else f"https://dev.azure.com/{value}"


def load_board(root):
    """The board settings: the config file's fields over what the git remote implies."""
    path = root / CONFIG_NAME
    config = {}
    if path.is_file():
        try:
            config = json.loads(path.read_text(encoding="utf-8-sig"))
        except ValueError as err:
            fail(f"{CONFIG_NAME} is not valid JSON.", str(err))
    remote = board_from_remote(git("remote", "get-url", "origin", cwd=root))
    organization = config.get("organization") or (remote[0] if remote else None)
    project = config.get("project") or (remote[1] if remote else None)
    if not organization or not project:
        fail(f"No Azure DevOps board set. Create {CONFIG_NAME} in the project with at least "
             '{ "organization": "<org>", "project": "<project>" }, or clone the repository from Azure DevOps.')
    return {
        "organization": normalise_organization(organization),
        "project": project,
        "team": config.get("team") or "",
        "areaPath": config.get("areaPath") or "",
        "azureSubscription": config.get("azureSubscription") or "",
        "excludeTypes": config.get("excludeTypes") or ["Epic", "Feature"],
        "capturesFolder": root / (config.get("capturesFolder") or "Artifacts/TicketProof"),
        "source": "config" if path.is_file() else "git remote",
    }


ROOT = None
BOARD = None


def board():
    global ROOT, BOARD
    if BOARD is None:
        ROOT = project_root()
        BOARD = load_board(ROOT)
    return BOARD


def is_scratch(ticket):
    return ticket >= FIRST_SCRATCH_TICKET


# --- the local record of a ticket's captures -----------------------------------

def ticket_folder(ticket):
    return board()["capturesFolder"] / str(ticket)


def manifest_path(ticket):
    return ticket_folder(ticket) / "manifest.json"


def load_manifest(ticket):
    path = manifest_path(ticket)
    if not path.is_file():
        return {"ticket": ticket, "captures": [], "posts": []}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        fail(f"The capture list for #{ticket} could not be read; something may be writing it. Try again.", str(path))


def save_manifest(ticket, manifest):
    path = manifest_path(ticket)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def pending(manifest):
    return [c for c in manifest.get("captures", []) if not c.get("postedCommentId")]


def kind_of(path):
    suffix = pathlib.Path(path).suffix.lower()
    if suffix in IMAGE_TYPES:
        return "image"
    if suffix in VIDEO_TYPES:
        return "video"
    return None


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- outlines and crops on images -----------------------------------------------

OUTLINE_COLOR = (255, 59, 48)


def parse_boxes(spec):
    """'x,y,w,h;x,y,w,h' in pixels of the original image, origin top-left."""
    boxes = []
    for part in (spec or "").split(";"):
        if not part.strip():
            continue
        try:
            x, y, w, h = (int(round(float(v))) for v in part.split(","))
        except ValueError:
            fail(f"'{part}' is not a box; write x,y,w,h in pixels, boxes separated by ';'.")
        if w <= 0 or h <= 0:
            fail(f"'{part}' has no size.")
        boxes.append((x, y, w, h))
    return boxes


def edit_image(path, outlines, crop):
    """Draws the outlines, then crops, in place, on the queued copy."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        fail("Outlining or cropping needs Pillow: pip install pillow.")
    with Image.open(path) as source:
        image = source.convert("RGB")
    thickness = max(3, round(min(image.size) / 200))
    draw = ImageDraw.Draw(image)
    for x, y, w, h in outlines:
        draw.rectangle([x, y, x + w - 1, y + h - 1], outline=OUTLINE_COLOR, width=min(thickness, w, h))
    if crop:
        x, y, w, h = crop
        image = image.crop((max(0, x), max(0, y), min(image.width, x + w), min(image.height, y + h)))
    image.save(path)


def attach(ticket, files, captions, label, outlines=None, crops=None, allow_duplicate=False, now=None):
    """Copies files into the ticket's folder and queues them for `post`. Originals are never changed."""
    for name, values in (("--caption", captions), ("--outline", outlines), ("--crop", crops)):
        if values and len(values) != len(files):
            fail(f"Give one {name} per --file ('' for none): {len(files)} files, {len(values)} given.")
    for i, path in enumerate(files):
        if not os.path.isfile(path):
            fail(f"There is no file at {path}.")
        kind = kind_of(path)
        if kind is None:
            fail(f"{os.path.basename(path)} is not an image or a clip ({', '.join(sorted(IMAGE_TYPES | VIDEO_TYPES))}).")
        if os.path.getsize(path) > MAX_UPLOAD_BYTES:
            fail(f"{os.path.basename(path)} is over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Trim or compress it first.")
        if kind == "video" and ((outlines and outlines[i]) or (crops and crops[i])):
            fail(f"{os.path.basename(path)} is a clip; outlines and crops are for images only.")

    manifest = load_manifest(ticket)
    digests = [file_digest(p) for p in files]
    if not allow_duplicate:
        known = {c.get("sourceSha256"): c for c in manifest.get("captures", []) if c.get("sourceSha256")}
        for path, digest in zip(files, digests):
            if digest in known:
                was = "already posted" if known[digest].get("postedCommentId") else "already waiting to post"
                fail(f"{os.path.basename(path)} is {was} on #{ticket}. Pass --allow-duplicate if it should go again.")
            known[digest] = {"file": path}

    folder = ticket_folder(ticket)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (now or dt.datetime.now()).replace(microsecond=0)
    queued = []
    for i, path in enumerate(files):
        boxes = parse_boxes(outlines[i]) if outlines else []
        crop = (parse_boxes(crops[i]) or [None])[0] if crops else None
        suffix = ".png" if (boxes or crop) else pathlib.Path(path).suffix.lower()
        number = len(manifest["captures"]) + 1
        while any((folder / f"{ticket}_{stamp:%Y%m%d-%H%M%S}_{number}{s}").exists() for s in (suffix, ".png")):
            number += 1   # a removed capture frees its number, but a later one may still hold the next
        name = f"{ticket}_{stamp:%Y%m%d-%H%M%S}_{number}{suffix}"
        shutil.copyfile(path, folder / name)
        if boxes or crop:
            edit_image(folder / name, boxes, crop)
        entry = {"file": name, "kind": kind_of(path), "caption": captions[i] if captions else "",
                 "label": label, "capturedAt": stamp.isoformat(), "sourceSha256": digests[i]}
        if boxes:
            entry["outlines"] = [list(b) for b in boxes]
        if crop:
            entry["crop"] = list(crop)
        manifest.setdefault("captures", []).append(entry)
        queued.append(entry)
    save_manifest(ticket, manifest)
    return queued


# --- the comment ------------------------------------------------------------------

def multiline(text):
    return "<br>".join(html.escape(line) for line in (text or "").strip().splitlines())


def read_body(path):
    """A --body file: an .html/.htm fragment as written; anything else as plain text."""
    if not path:
        return ""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as err:
        fail(f"Could not read the --body file {path}.", str(err))
    if not text.strip():
        return ""
    return text.strip() if pathlib.Path(path).suffix.lower() in (".html", ".htm") else f"<div>{multiline(text)}</div>"


def build_comment(captures, urls, note, commit, day, body=""):
    """The opening line, the optional body, each capture with its caption, then the marker line."""
    parts = [f"<div><b>After:</b> {multiline(note)}</div>" if (note or "").strip() else "<div><b>After</b></div>"]
    if body:
        parts.append(f"<div><br>{body}</div>")
    for capture, url in zip(captures, urls):
        src = html.escape(url, quote=True)
        label = html.escape(capture.get("label") or "")
        if capture.get("kind") == "video":
            parts.append(f'<div><br>&#9654; <a href="{src}">Clip: {label or html.escape(capture["file"])}</a></div>')
        else:
            parts.append(f'<div><br><img src="{src}" alt="{html.escape("After: " + (capture.get("label") or ""), quote=True)}"></div>')
        grey = f'<span style="color:#888;font-size:11px">{label}</span>' if label else ""
        caption = multiline(capture.get("caption") or "")
        if caption or grey:
            parts.append(f"<div>{caption}{'<br>' if caption and grey else ''}{grey}</div>")
    footer = " · ".join(p for p in (MARKER, html.escape(commit), day) if p)
    parts.append(f'<div><br><span style="color:#888;font-size:11px">{footer}</span></div>')
    return "".join(parts)


PREVIEW_PAGE = """<!doctype html><meta charset="utf-8"><title>Preview: #{ticket}</title>
<style>body{{font:14px "Segoe UI",sans-serif;background:#f4f4f4;margin:24px}}.note{{color:#a15c00}}
.comment{{background:#fff;border:1px solid #ddd;border-radius:4px;padding:12px 16px;max-width:860px}}
.comment img{{max-width:100%}}</style><p class="note">Preview only. Nothing has been posted to #{ticket}.</p>
<div class="comment">{body}</div>"""


def commit_label():
    sha = git("rev-parse", "--short=8", "HEAD", cwd=ROOT)
    if not sha:
        return ""
    return f"{sha}+local changes" if git("status", "--porcelain", "--untracked-files=no", cwd=ROOT) else sha


# --- Azure DevOps ----------------------------------------------------------------

_token = os.environ.get("ADO_ACCESS_TOKEN") or None


def az_command():
    for name in ("az", "az.cmd"):
        found = shutil.which(name)
        if found:
            return [found]
    fail("The Azure CLI is not installed. Install it from https://aka.ms/installazurecliwindows, then try again.")


NOT_SIGNED_IN = "You are not signed in to Azure DevOps. Run `az login` in a terminal, then try again."


def token():
    global _token
    if _token is None:
        args = [*az_command(), "account", "get-access-token", "--resource", ADO_RESOURCE, "-o", "json"]
        if board()["azureSubscription"]:
            args += ["--subscription", board()["azureSubscription"]]
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or not proc.stdout.strip():
            fail(NOT_SIGNED_IN, proc.stderr.strip())
        _token = json.loads(proc.stdout)["accessToken"]
    return _token


def api_url(path, version=API, **query):
    b = board()
    query["api-version"] = version
    return f"{b['organization']}/{urllib.parse.quote(b['project'])}/_apis/{path}?{urllib.parse.urlencode(query)}"


def http_error_message(code, url):
    if code in (401, 203):
        return NOT_SIGNED_IN
    if code == 403:
        return f"Your account cannot change tickets in {board()['project']}. Ask the project admin for Contributor access."
    if code == 404 and "/workitems/" in url.lower():
        ticket = url.lower().split("/workitems/")[1].split("/")[0].split("?")[0]
        return f"Ticket #{ticket} does not exist in {board()['project']}, or your account cannot see it."
    if code == 404:
        return f"{board()['project']} was not found in {board()['organization']}. Check {CONFIG_NAME}."
    if code == 413:
        return "A file is too large for Azure DevOps. Trim or compress it, then post again."
    return f"Azure DevOps returned an error (HTTP {code}). Try again; if it keeps happening, read the detail below."


def request(method, url, body=None, content_type="application/json"):
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token()}", "Content-Type": content_type, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read()
            # A rejected token gets a 203 sign-in page, not a 401.
            if resp.status == 203 or "json" not in resp.headers.get("Content-Type", "json"):
                fail(NOT_SIGNED_IN, f"{method} {url.split('?')[0]} returned a sign-in page.")
        return json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:500]
        fail(http_error_message(err.code, url), f"{method} {url.split('?')[0]}: HTTP {err.code}\n{detail}")
    except (urllib.error.URLError, TimeoutError) as err:
        fail("Could not reach Azure DevOps. Check your network or VPN, then try again.", str(err))


def ticket_summary(item):
    f = item["fields"]
    assigned = f.get("System.AssignedTo") or {}
    return {"id": item["id"], "title": f.get("System.Title", ""), "state": f.get("System.State", ""),
            "type": f.get("System.WorkItemType", ""), "iteration": f.get("System.IterationPath", ""),
            "area": f.get("System.AreaPath", ""),
            "assignedTo": assigned.get("displayName", "") if isinstance(assigned, dict) else str(assigned),
            "url": f"{board()['organization']}/{urllib.parse.quote(board()['project'])}/_workitems/edit/{item['id']}"}


def plain_text(markup):
    text = re.sub(r"<(br|/p|/div|/li)\b[^>]*>", "\n", markup or "", flags=re.I)
    return re.sub(r"\n\s*\n+", "\n", html.unescape(re.sub(r"<[^>]+>", "", text))).strip()


def get_work_item(ticket, extra=()):
    return request("GET", api_url(f"wit/workitems/{ticket}", fields=",".join(WORK_ITEM_FIELDS + list(extra))))


def get_comments(ticket):
    comments = request("GET", api_url(f"wit/workItems/{ticket}/comments", COMMENTS_API)).get("comments") or []
    out = []
    for c in sorted(comments, key=lambda c: c.get("createdDate") or ""):
        markup = c.get("text") or ""
        out.append({"author": (c.get("createdBy") or {}).get("displayName", ""), "date": (c.get("createdDate") or "")[:10],
                    "text": plain_text(markup)[:1500], "images": len(re.findall(r"<img\b", markup, re.I)),
                    "proof": MARKER in markup})
    return out


def sprints():
    """Dated iterations, oldest first: the team's when a team is set, else the project's."""
    b = board()
    if b["team"]:
        url = (f"{b['organization']}/{urllib.parse.quote(b['project'])}/{urllib.parse.quote(b['team'])}"
               f"/_apis/work/teamsettings/iterations?api-version={API}")
        values = request("GET", url).get("value") or []
        out = [{"name": v["name"], "path": v["path"], "start": (v["attributes"].get("startDate") or "")[:10],
                "finish": (v["attributes"].get("finishDate") or "")[:10]} for v in values]
    else:
        tree = request("GET", api_url("wit/classificationnodes/Iterations", **{"$depth": 10}))
        out = []

        def walk(node):
            attrs = node.get("attributes") or {}
            if attrs.get("startDate") and attrs.get("finishDate"):
                parts = [p for p in node["path"].split("\\") if p and p != "Iteration"]
                out.append({"name": node["name"], "path": "\\".join(parts),
                            "start": attrs["startDate"][:10], "finish": attrs["finishDate"][:10]})
            for child in node.get("children") or []:
                walk(child)
        walk(tree)
    return sorted((s for s in out if s["start"] and s["finish"]), key=lambda s: s["start"])


def current_sprint(all_sprints, today):
    """The sprint containing today, else the latest one already started."""
    started = [s for s in all_sprints if s["start"] <= today]
    for s in reversed(started):
        if today <= s["finish"]:
            return s
    return started[-1] if started else None


def sprint_wiql(iteration_path, mine, area="", exclude=()):
    q = lambda v: v.replace("'", "''")
    where = [f"[System.IterationPath] UNDER '{q(iteration_path)}'", "[System.State] <> 'Removed'"]
    if exclude:
        where.append("[System.WorkItemType] NOT IN (" + ", ".join(f"'{q(t)}'" for t in exclude) + ")")
    if area:
        where.append(f"[System.AreaPath] UNDER '{q(area)}'")
    if mine:
        where.append("[System.AssignedTo] = @Me")
    return "SELECT [System.Id] FROM WorkItems WHERE " + " AND ".join(where) + " ORDER BY [System.ChangedDate] DESC"


def query_ids(wiql):
    return [row["id"] for row in request("POST", api_url("wit/wiql"), {"query": wiql}).get("workItems", [])]


def get_work_items(ids):
    items = []
    for start in range(0, len(ids), 200):
        batch = ",".join(str(i) for i in ids[start:start + 200])
        items += request("GET", api_url("wit/workitems", ids=batch, fields=",".join(WORK_ITEM_FIELDS)))["value"]
    return [ticket_summary(i) for i in items]


def upload(path, file_name):
    with open(path, "rb") as fh:
        result = request("POST", api_url("wit/attachments", fileName=file_name), fh.read(),
                         content_type="application/octet-stream")
    return f"{result['url']}?{urllib.parse.urlencode({'fileName': file_name})}"


def link_attachments(ticket, urls, note):
    ops = [{"op": "add", "path": "/relations/-", "value": {
        "rel": "AttachedFile", "url": url.split("?")[0],
        "attributes": {"comment": f"{MARKER}{': ' + note if note else ''}"}}} for url in urls]
    request("PATCH", api_url(f"wit/workitems/{ticket}"), ops, content_type="application/json-patch+json")


def mark_done(ticket, item):
    """Moves the ticket to its type's completed state, looked up because processes name it differently."""
    states = request("GET", api_url(f"wit/workitemtypes/{urllib.parse.quote(item['type'])}/states"))["value"]
    done = next((s["name"] for s in states if s.get("category") == "Completed"), None)
    if done is None:
        fail(f"{item['type']} tickets have no finished state on this board, so #{ticket} was left as it is.")
    if item["state"] == done:
        return done
    updated = request("PATCH", api_url(f"wit/workitems/{ticket}"),
                      [{"op": "add", "path": "/fields/System.State", "value": done}],
                      content_type="application/json-patch+json")
    return updated["fields"]["System.State"]


# --- commands ----------------------------------------------------------------------

def out(payload):
    print(json.dumps(payload, ensure_ascii=False, default=str))


def cmd_doctor(args):
    checks = []

    def check(name, probe, fix):
        try:
            checks.append({"name": name, "ok": True, "detail": probe() or ""})
        except SystemExit as err:
            checks.append({"name": name, "ok": False, "detail": str(err).splitlines()[0] if str(err) else "", "fix": fix})
        return checks[-1]["ok"]

    ok = check("Python 3.9 or newer", lambda: sys.version.split()[0] if sys.version_info >= (3, 9) else fail("too old"),
               "Install Python 3.12 from python.org.")
    ok = ok and check("Board settings", lambda: f"{board()['project']} in {board()['organization']} (from {board()['source']})",
                      f"Create {CONFIG_NAME} with organization and project.")
    ok = ok and check("Azure CLI installed", lambda: az_command()[0], "Install it from https://aka.ms/installazurecliwindows.")
    ok = ok and check("Signed in to Azure DevOps", lambda: token() and "", "Run `az login` and sign in.")
    if ok:
        check("Access to the board", lambda: f"{len(sprints())} dated sprint(s)",
              "Ask the project admin to add you to the Azure DevOps project, and check the project name.")
    out({"ok": all(c["ok"] for c in checks), "checks": checks})


def cmd_tickets(args):
    b = board()
    all_sprints = sprints()
    today = dt.date.today().isoformat()
    sprint = current_sprint(all_sprints, today)
    if args.sprint:
        sprint = next((s for s in all_sprints if s["name"] == args.sprint), None)
        if sprint is None:
            fail(f"No sprint named {args.sprint!r}. Recent: {', '.join(s['name'] for s in all_sprints[-5:])}")
    if sprint is None:
        fail(f"{b['project']} has no dated sprint that has started yet. Set dates on its iterations.")
    ids = query_ids(sprint_wiql(sprint["path"], False, b["areaPath"], b["excludeTypes"]))
    mine = set(query_ids(sprint_wiql(sprint["path"], True, b["areaPath"], b["excludeTypes"]))) if ids else set()
    tickets = get_work_items(ids) if ids else []
    rank = {i: n for n, i in enumerate(ids)}
    tickets.sort(key=lambda t: (t["state"] in FINISHED_STATES, rank.get(t["id"], 0)))
    for t in tickets:
        t["mine"] = t["id"] in mine
    out({"sprint": sprint, "recent": [s["name"] for s in all_sprints if s["start"] <= today][-3:], "tickets": tickets})


def cmd_lookup(args):
    item = get_work_item(args.ticket, ["System.Description", "System.Tags"])
    details = ticket_summary(item)
    details["description"] = plain_text(item["fields"].get("System.Description"))[:2000]
    details["tags"] = [t.strip() for t in (item["fields"].get("System.Tags") or "").split(";") if t.strip()]
    details["comments"] = get_comments(args.ticket)
    details["waitingToPost"] = len(pending(load_manifest(args.ticket)))
    out(details)


def cmd_attach(args):
    queued = attach(args.ticket, args.file, args.caption or [], args.label, args.outline, args.crop, args.allow_duplicate)
    out({"ticket": args.ticket, "queued": queued, "waiting": len(pending(load_manifest(args.ticket))),
         "folder": str(ticket_folder(args.ticket))})


def cmd_status(args):
    manifest = load_manifest(args.ticket)
    waiting = pending(manifest)
    folder = ticket_folder(args.ticket)
    out({"ticket": args.ticket, "folder": str(folder),
         "waiting": [{**c, "path": str(folder / c["file"])} for c in waiting],
         "missing": [c["file"] for c in waiting if not (folder / c["file"]).is_file()],
         "posts": manifest.get("posts", [])})


def cmd_remove(args):
    manifest = load_manifest(args.ticket)
    match = [c for c in pending(manifest) if c["file"] == args.file]
    if not match:
        fail(f"{args.file} is not waiting to post on #{args.ticket}. `status` lists what is.")
    manifest["captures"].remove(match[0])
    save_manifest(args.ticket, manifest)
    path = ticket_folder(args.ticket) / args.file
    if path.is_file():
        path.unlink()
    out({"ticket": args.ticket, "removed": args.file, "waiting": len(pending(manifest))})


def cmd_post(args):
    ticket = args.ticket
    if is_scratch(ticket) and not (args.preview or args.dry_run):
        fail(f"#{ticket} is a scratch ticket for tests; nothing posts from it.")
    manifest = load_manifest(ticket)
    captures = pending(manifest)
    body = read_body(args.body)
    if not captures and not body:
        fail(f"Nothing to post for #{ticket}: no captures are waiting. Attach some, or pass --body.")
    folder = ticket_folder(ticket)
    missing = [c["file"] for c in captures if not (folder / c["file"]).is_file()]
    if missing:
        fail("Some waiting files are missing from disk. Remove them, then post again.", "\n".join(missing))
    day = (max(c.get("capturedAt", "") for c in captures) if captures else dt.date.today().isoformat())[:10]
    commit = commit_label()

    if args.preview or args.dry_run:
        urls = [(folder / c["file"]).resolve().as_uri() for c in captures]
        comment = build_comment(captures, urls, args.note, commit, day, body)
        if args.dry_run:
            print(comment)
            return
        page = folder / "preview.html"
        folder.mkdir(parents=True, exist_ok=True)
        page.write_text(PREVIEW_PAGE.format(ticket=ticket, body=comment), encoding="utf-8")
        out({"ticket": ticket, "preview": str(page)})
        return

    item = ticket_summary(get_work_item(ticket))
    earlier = len(manifest.get("posts", []))
    if item["state"] in FINISHED_STATES and earlier and not args.again:
        fail(f"#{ticket} is already {item['state']} and has {earlier} proof comment(s) from this tool. "
             "Pass --again only if this adds something new.")
    urls = [upload(folder / c["file"], c["file"]) for c in captures]
    if urls:
        link_attachments(ticket, urls, args.note or "")
    comment = request("POST", api_url(f"wit/workItems/{ticket}/comments", COMMENTS_API),
                      {"text": build_comment(captures, urls, args.note, commit, day, body)})
    stored = request("GET", api_url(f"wit/workItems/{ticket}/comments/{comment['id']}", COMMENTS_API)).get("text", "")
    images = sum(1 for c in captures if c.get("kind") != "video")
    if MARKER not in stored or stored.count("<img") < images:
        fail(f"Comment {comment['id']} on #{ticket} was saved without its marker or images. Check the ticket before posting again.")

    posted_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for capture, url in zip(captures, urls):
        capture.update(postedCommentId=comment["id"], attachmentUrl=url, postedAt=posted_at)
    manifest.setdefault("posts", []).append({"commentId": comment["id"], "postedAt": posted_at, "note": args.note or "",
                                             "commit": commit, "count": len(captures)})
    manifest["title"] = item["title"]
    save_manifest(ticket, manifest)

    result = {"ticket": ticket, "title": item["title"], "commentId": comment["id"], "files": len(captures),
              "url": item["url"], "state": item["state"]}
    if args.done:
        try:
            result["state"] = mark_done(ticket, item)
        except SystemExit as err:   # the comment is already on the ticket, so a refused state change is reported
            result["doneError"] = str(err).splitlines()[0] if str(err) else "The board refused the change."
    out(result)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check settings, the Azure CLI, sign-in and board access.").set_defaults(func=cmd_doctor)

    p = sub.add_parser("tickets", help="List the current sprint's tickets, flagging yours.")
    p.add_argument("--sprint", help='A sprint by name, e.g. "Sprint 3". Defaults to the current one.')
    p.set_defaults(func=cmd_tickets)

    p = sub.add_parser("lookup", help="A ticket's title, state, description and comments.")
    p.add_argument("--ticket", type=int, required=True)
    p.set_defaults(func=cmd_lookup)

    p = sub.add_parser("attach", help="Queue images or clips for a ticket.")
    p.add_argument("--ticket", type=int, required=True)
    p.add_argument("--file", nargs="+", required=True, help="Images or clips, in the order they should appear.")
    p.add_argument("--caption", nargs="+", help="One caption per file.")
    p.add_argument("--label", default="", help='Grey line under each file, naming the screen, e.g. "Ward 2 · hand-wash station".')
    p.add_argument("--outline", nargs="+", help="Per image: boxes 'x,y,w,h;x,y,w,h' in its pixels, or '' for none.")
    p.add_argument("--crop", nargs="+", help="Per image: 'x,y,w,h' to keep, or '' for all. Applied after outlining.")
    p.add_argument("--allow-duplicate", action="store_true", help="Queue a file even if it is already waiting or posted.")
    p.set_defaults(func=cmd_attach)

    p = sub.add_parser("status", help="What is waiting to post for a ticket. No network.")
    p.add_argument("--ticket", type=int, required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("remove", help="Drop one waiting file from a ticket.")
    p.add_argument("--ticket", type=int, required=True)
    p.add_argument("--file", required=True, help="Its name, as `status` lists it.")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("post", help="Post the waiting files as one comment on the ticket.")
    p.add_argument("--ticket", type=int, required=True)
    p.add_argument("--note", default="", help="One line saying what the files show now.")
    p.add_argument("--body", help="A file placed between the opening line and the files: .html as written, else plain text.")
    p.add_argument("--preview", action="store_true", help="Write the comment as a local page and post nothing.")
    p.add_argument("--dry-run", action="store_true", help="Print the comment HTML and post nothing.")
    p.add_argument("--done", action="store_true", help="After posting, move the ticket to its finished state.")
    p.add_argument("--again", action="store_true", help="Post even though the ticket is finished and already has proof.")
    p.set_defaults(func=cmd_post)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
