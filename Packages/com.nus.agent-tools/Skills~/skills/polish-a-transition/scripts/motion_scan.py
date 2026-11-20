"""Scan a Unity activity for motion and feedback smells, as a starting point for a polish audit.

    python motion_scan.py <prefab | .cs file | folder> [...] [--detail] [--json]

Give the activity's prefab(s) where you can: the scanner then scans exactly the scripts those prefabs use (found
through their m_Script guids), plus the prefabs themselves, which hold half the motion wiring. A folder scans
every .cs file under it, which is too much when one folder holds several activities.

Colour literals and direct scale writes are common and mostly harmless, so they are summarised per file unless
--detail lists every line.

Each hit is a lead, not a verdict: confirm it in context before it goes into an audit (SKILL.md, step 3).
Standard library only.
"""
import json
import os
import re
import sys

# rule id -> (title, what to check before calling it a finding)
RULES = {
    "scaled-time": ("Scaled time in UI motion",
                    "Only a problem if something sets Time.timeScale to 0; search for writes to it first."),
    "yield-alloc": ("New yield object inside a coroutine loop",
                    "Allocates every pass of the loop; cache it (static readonly)."),
    "frame-search": ("Scene search or GetComponent in per-frame code",
                     "Per-frame code here means Update, LateUpdate, OnGUI, OnDrag and loops inside coroutines. "
                     "Fine if guarded to run once."),
    "frame-alloc": ("Allocation in per-frame code",
                    "new List / LINQ / string building in per-frame code allocates every frame."),
    "base-skipped": ("Override of a shared input handler without a base call",
                     "Check what the base does (sounds, eased return, feedback hooks) and whether anything here needs it."),
    "colour-literal": ("Hard-coded colour",
                       "Verdict, attention and state colours should come from the project's theme tokens."),
    "direct-scale": ("Scale written directly",
                     "Hover and press scaling belongs to the shared feedback component, not hand-written code."),
    "instant-show": ("Panel shown with an instant SetActive(true)",
                     "Fine for a panel that fades itself in on enable; a pop-in otherwise."),
    "feedback-fight": ("Two feedback components drive the same target (prefab)",
                       "Both write the same property, so the last to run wins and the motion stutters or sticks."),
    "inspector-toggle": ("Shown or hidden by an inspector event (prefab)",
                         "A persistent SetActive call is an instant pop; code reading won't find it."),
    "feedback-values": ("Feedback values in use (prefab)",
                        "Compare each with the project's motion vocabulary; a one-off value is an inconsistency."),
}

FRAME_METHODS = re.compile(r"\bvoid\s+(Update|LateUpdate|FixedUpdate|OnGUI|OnDrag)\s*\(")
COROUTINE = re.compile(r"\bIEnumerator\s+\w+\s*\(")
LOOP = re.compile(r"^\s*(while|for|foreach|do)\b")
INPUT_OVERRIDE = re.compile(
    r"\boverride\s+void\s+(OnBeginDrag|OnDrag|OnEndDrag|OnDrop|OnPointerEnter|OnPointerExit|OnPointerDown|OnPointerUp|OnPointerClick)\s*\(")
SEARCH = re.compile(r"\b(GameObject\.Find\w*|Find(Any|First)?ObjectsOfType|Find(Any|First)ObjectByType|FindObjectsByType|GetComponents?(InChildren|InParent)?\s*<)")
ALLOC = re.compile(r"\bnew\s+(List|Dictionary|HashSet)\s*<|\.(Where|Select|ToList|ToArray|OrderBy)\s*\(|string\.Format\s*\(|\$\"")
SCALED = re.compile(r"\bTime\.(deltaTime|time)\b")
YIELD_NEW = re.compile(r"yield\s+return\s+new\s+(WaitForEndOfFrame|WaitForSeconds|WaitForFixedUpdate)\s*\(")
COLOUR = re.compile(r"\bnew\s+Color(32)?\s*\(\s*[\d.]")
SCALE_SET = re.compile(r"\.localScale\s*=")
SHOW = re.compile(r"(\w*(Panel|Popup|Window|Modal|Overlay|Dialog)\w*)\s*(\.gameObject)?\s*\.SetActive\s*\(\s*true\s*\)", re.I)

FEEDBACK_VALUE = re.compile(r"^\s{2}(\w*(?:[Ss]cale|[Ss]peed|[Dd]uration|[Oo]ffset)\w*):\s*(.+)$")
TARGET_FIELD = re.compile(r"^\s{2}(\w*(?:[Ll]ocator|[Tt]arget)\w*):\s*\{fileID:\s*(-?\d+)")


# ---------------------------------------------------------------- C#

def strip_comment(line):
    cut = line.find("//")
    return line if cut < 0 else line[:cut]


def block_end(lines, start):
    """Line index where the brace block opened at or after `start` closes."""
    depth, opened, j = 0, False, start
    while j < len(lines):
        code = strip_comment(lines[j])
        depth += code.count("{") - code.count("}")
        opened = opened or "{" in code
        if opened and depth <= 0:
            return j
        j += 1
    return len(lines) - 1


def method_bodies(lines, header):
    """Yield (start, end) line ranges, 0-based inclusive, of methods whose header matches."""
    i = 0
    while i < len(lines):
        if header.search(lines[i]):
            j = block_end(lines, i)
            yield i, j
            i = j + 1
        else:
            i += 1


def per_frame_lines(lines):
    frame = set()
    for start, end in method_bodies(lines, FRAME_METHODS):
        frame.update(range(start, end + 1))
    for start, end in method_bodies(lines, COROUTINE):
        n = start + 1
        while n <= end:
            if LOOP.match(strip_comment(lines[n])):
                loop_end = min(block_end(lines, n), end)
                frame.update(range(n, loop_end + 1))
                n = loop_end + 1
            else:
                n += 1
    return frame


def scan_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    hits = []

    def add(rule, n):
        hits.append({"rule": rule, "file": path, "line": n + 1, "code": lines[n].strip()[:140]})

    frame_lines = per_frame_lines(lines)

    for start, end in method_bodies(lines, INPUT_OVERRIDE):
        body = "\n".join(strip_comment(l) for l in lines[start:end + 1])
        name = INPUT_OVERRIDE.search(lines[start]).group(1)
        if not re.search(r"\bbase\." + name + r"\s*\(", body):
            add("base-skipped", start)

    for n, raw in enumerate(lines):
        code = strip_comment(raw)
        if not code.strip():
            continue
        if SCALED.search(code):
            add("scaled-time", n)
        if COLOUR.search(code):
            add("colour-literal", n)
        if SCALE_SET.search(code):
            add("direct-scale", n)
        if SHOW.search(code):
            add("instant-show", n)
        if n in frame_lines:
            if YIELD_NEW.search(code):
                add("yield-alloc", n)
            if SEARCH.search(code):
                add("frame-search", n)
            if ALLOC.search(code):
                add("frame-alloc", n)
    return hits


# ---------------------------------------------------------------- prefabs

_script_index = {}


def project_root(path):
    parts = os.path.abspath(path).replace("\\", "/").split("/")
    if "Assets" in parts:
        return "/".join(parts[:parts.index("Assets")])
    return None


def script_index(root, wanted):
    """guid -> .cs path for the wanted guids, searching Assets then Packages and stopping once all are found."""
    index = _script_index.setdefault(root, {})
    missing = set(wanted) - set(index)
    if not missing:
        return index
    for top in ("Assets", "Packages"):
        for dirpath, dirs, files in os.walk(os.path.join(root, top)):
            dirs[:] = [d for d in dirs if d not in ("Library", "Temp")]
            for name in files:
                if not name.endswith(".cs.meta"):
                    continue
                try:
                    with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as f:
                        m = re.search(r"^guid:\s*([0-9a-f]{32})", f.read(300), re.M)
                except OSError:
                    continue
                if m:
                    index[m.group(1)] = os.path.join(dirpath, name[:-5])
                    missing.discard(m.group(1))
                    if not missing:
                        return index
    return index


def prefab_script_guids(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return set(re.findall(r"m_Script:\s*\{fileID:\s*\d+,\s*guid:\s*([0-9a-f]{32})", f.read()))


def yaml_docs(text):
    """(fileID, lines) for each document in a Unity YAML file."""
    docs, current_id, current = [], None, []
    for line in text.splitlines():
        m = re.match(r"^--- !u!\d+ &(-?\d+)", line)
        if m:
            if current_id is not None:
                docs.append((current_id, current))
            current_id, current = m.group(1), []
        elif current_id is not None:
            current.append(line)
    if current_id is not None:
        docs.append((current_id, current))
    return docs


def scan_prefab(path, index):
    """Prefab-level leads, plus the script paths the prefab uses."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    lines = text.splitlines()
    hits, scripts = [], set()
    names = {}          # GameObject fileID -> name
    transform_of = {}   # Transform / RectTransform fileID -> its GameObject fileID
    for doc_id, body in yaml_docs(text):
        kind = body[0] if body else ""
        for line in body:
            m = re.match(r"^\s{2}m_Name:\s*(.*)$", line)
            if m and kind.startswith("GameObject"):
                names[doc_id] = m.group(1).strip()
            g = re.match(r"^\s{2}m_GameObject:\s*\{fileID:\s*(-?\d+)", line)
            if g and kind.startswith(("Transform", "RectTransform")):
                transform_of[doc_id] = g.group(1)

    def line_of(needle, after=0):
        for n in range(after, len(lines)):
            if needle in lines[n]:
                return n + 1
        return 0

    targets = {}  # (script, target id) -> [(object, line)]
    values = {}   # (script, field) -> {value: first line}
    for doc_id, body in yaml_docs(text):
        joined = "\n".join(body)
        sm = re.search(r"m_Script:\s*\{fileID:\s*\d+,\s*guid:\s*([0-9a-f]{32})", joined)
        if not sm:
            continue
        script = index.get(sm.group(1))
        if script:
            scripts.add(script)
        script_name = os.path.splitext(os.path.basename(script))[0] if script else ""
        go = re.search(r"m_GameObject:\s*\{fileID:\s*(-?\d+)", joined)
        owner = names.get(go.group(1), "?") if go else "?"
        doc_line = line_of(f"&{doc_id}")
        if script_name.endswith("Feedback"):
            # What it actually drives: its target field resolved to a GameObject, or its own GameObject when unset.
            driven = go.group(1) if go else doc_id
            for line in body:
                tm = TARGET_FIELD.match(line)
                if tm and tm.group(2) != "0":
                    driven = transform_of.get(tm.group(2), tm.group(2))
                    break
            targets.setdefault((script_name, driven), []).append((owner, doc_line))
            for line in body:
                vm = FEEDBACK_VALUE.match(line)
                if vm:
                    values.setdefault((script_name, vm.group(1)), {}).setdefault(vm.group(2).strip(), doc_line)
        for n, line in enumerate(body):
            if re.match(r"^\s+m_MethodName:\s*SetActive\s*$", line):
                hits.append({"rule": "inspector-toggle", "file": path, "line": doc_line,
                             "code": f"{owner}: {script_name or 'component'} event calls SetActive"})

    for (script_name, _), owners in targets.items():
        if len(owners) > 1:
            who = ", ".join(sorted({o for o, _ in owners}))
            hits.append({"rule": "feedback-fight", "file": path, "line": owners[1][1],
                         "code": f"{len(owners)} {script_name} components share one target (on {who})"})
    for (script_name, field), seen in sorted(values.items()):
        listed = ", ".join(sorted(seen))
        hits.append({"rule": "feedback-values", "file": path, "line": min(seen.values()),
                     "code": f"{script_name}.{field}: {listed}"})
    return hits, scripts


# ---------------------------------------------------------------- driver

def cs_files(target):
    if os.path.isfile(target):
        if target.endswith(".cs"):
            yield target
        return
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in ("Library", "Temp", "obj", ".git") and "Tests" not in d]
        for name in files:
            if name.endswith(".cs"):
                yield os.path.join(root, name)


def own_script(path):
    """A project script, not a package's or Unity's own, so prefab mode doesn't scan the whole framework."""
    p = path.replace("\\", "/")
    return "/Library/" not in p and "/Tests/" not in p


SUMMARISED = ("colour-literal", "direct-scale")


def main(argv):
    as_json = "--json" in argv
    detail = "--detail" in argv
    targets = [a for a in argv if a not in ("--json", "--detail")]
    if not targets:
        print(__doc__.strip())
        return 2

    hits, scripts = [], set()
    for target in targets:
        if not os.path.exists(target):
            print(f"Not found: {target}", file=sys.stderr)
            return 2
        if target.endswith(".prefab"):
            root = project_root(target)
            if root is None:
                print(f"Can't find the project's Assets folder above {target}", file=sys.stderr)
                return 2
            prefab_hits, used = scan_prefab(target, script_index(root, prefab_script_guids(target)))
            hits.extend(prefab_hits)
            scripts.update(s for s in used if own_script(s))
        else:
            scripts.update(cs_files(target))
    for path in sorted(scripts):
        hits.extend(scan_file(path))

    if as_json:
        print(json.dumps(hits, indent=2))
        return 0
    if not hits:
        print("No motion smells found.")
        return 0
    print(f"Scanned {len(scripts)} script(s).")
    for rule, (title, check) in RULES.items():
        group = [h for h in hits if h["rule"] == rule]
        if not group:
            continue
        print(f"\n## {title} ({len(group)})\n_{check}_\n")
        if rule in SUMMARISED and not detail:
            counts = {}
            for h in group:
                counts[h["file"]] = counts.get(h["file"], 0) + 1
            for path, count in sorted(counts.items(), key=lambda kv: -kv[1]):
                print(f"- `{path}`: {count}")
            continue
        for h in group:
            print(f"- `{h['file']}:{h['line']}`  {h['code']}")
    print(f"\n{len(hits)} lead(s). Confirm each in context before it becomes a finding.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
