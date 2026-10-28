"""
Edit Unity scene and prefab YAML without collateral damage.

Saving a .unity or .prefab from the editor can rewrite far more than you changed (Visual Scripting graph
JSON, object-reference lists, nested-prefab modifications, newly added fields). These commands let you
keep exactly the change you meant and nothing else.

    python scene_yaml.py check  Assets/Scenes/Main.unity [--max-lines 60]
    python scene_yaml.py blocks Assets/Scenes/Main.unity --changed
    python scene_yaml.py splice Assets/Scenes/Main.unity --ids 1663899483,1663899484 [--base HEAD] [--dry-run]
    python scene_yaml.py remove-mod "Assets/Prefabs/HUD.prefab" --target 2879267707569496181 \
        --guid 5a158c42f9c5cb143b8d690e5969de0b --prop m_AnchorMin.y [--value 0] [--dry-run]

Every write preserves the file's line endings and refuses unless each change matches exactly once.
Run from anywhere inside the git repository. Paths are relative to the current directory.
"""

import argparse
import os
import re
import subprocess
import sys

HEADER = re.compile(r"^--- !u!(\d+) &(-?\d+)( stripped)?", re.M)

# Lines that are noise when they change on their own: they belong to serialized blobs Unity rewrites on
# save (Visual Scripting graphs) rather than to anything a person authored.
CHURN_MARKERS = ("_json:", "$content", "$type", "$version", "\"guid\":")


def newline_of(text):
    return "\r\n" if "\r\n" in text[:20000] else "\n"


def read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def git(*args, check=True):
    result = subprocess.run(["git", *args], capture_output=True)
    if check and result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout.decode("utf-8", "replace")


def base_text(path, rev):
    """The file at REV, in the working copy's line endings: with core.autocrlf the blob is LF while the
    checkout is CRLF, and comparing the two would mark every block as changed."""
    # "./" makes git resolve the path relative to the current directory, not the repository root.
    text = git("show", f"{rev}:./{path.replace(os.sep, '/')}")
    lf = text.replace("\r\n", "\n")
    return lf.replace("\n", "\r\n") if newline_of(read(path)) == "\r\n" else lf


def split_blocks(text):
    """(preamble, [(fileID, block_text)]) — a block runs from its '--- !u!' header to the next one."""
    starts = [m.start() for m in HEADER.finditer(text)]
    if not starts:
        return text, []
    preamble = text[:starts[0]]
    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end]
        blocks.append((HEADER.match(chunk).group(2), chunk))
    return preamble, blocks


def block_name(block, all_blocks):
    """Best-effort human name for a block: its own m_Name, or its GameObject's."""
    m = re.search(r"^  m_Name: (.+)$", block, re.M)
    if m and m.group(1).strip():
        return m.group(1).strip()
    go = re.search(r"m_GameObject: \{fileID: (-?\d+)\}", block)
    if go:
        for fid, other in all_blocks:
            if fid == go.group(1):
                n = re.search(r"^  m_Name: (.+)$", other, re.M)
                if n:
                    return n.group(1).strip()
    cls = re.search(r"m_EditorClassIdentifier: [^:]*::(\S+)", block)
    return cls.group(1) if cls else ""


# ───────────────────────────── check ─────────────────────────────

def cmd_check(args):
    numstat = git("diff", "--numstat", args.base, "--", args.file).strip()
    if not numstat:
        print(f"{args.file}: no changes against {args.base}.")
        return 0
    added, removed, _ = numstat.split("\t", 2)
    diff = git("diff", "-U0", args.base, "--", args.file)
    changed = [l for l in diff.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    churn = [l for l in changed if any(m in l for m in CHURN_MARKERS)]
    hunks = diff.count("\n@@")

    print(f"{args.file}: +{added} -{removed} in {hunks} hunk(s) against {args.base}.")
    if churn:
        print(f"  {len(churn)} changed line(s) are serialized-graph churn (Visual Scripting JSON and similar).")
    total = int(added) + int(removed) if added.isdigit() and removed.isdigit() else len(changed)
    if churn or total > args.max_lines:
        print("  LOOKS LIKE A UNITY SAVE REWROTE THE FILE. Keep only your change: revert the file and re-apply "
              "it as a text edit, or use `splice` for a structural change. Do not commit this diff.")
        return 1
    print("  Within the expected size. Read the diff before committing: `git diff -- <file>`.")
    return 0


# ───────────────────────────── blocks ─────────────────────────────

def cmd_blocks(args):
    _, new_blocks = split_blocks(read(args.file))
    if args.changed:
        _, old_blocks = split_blocks(base_text(args.file, args.base))
        old = dict(old_blocks)
        new = dict(new_blocks)
        for fid, block in new_blocks:
            if fid not in old:
                print(f"added    {fid}  {block.splitlines()[0][4:]:<28} {block_name(block, new_blocks)}")
            elif old[fid] != block:
                print(f"changed  {fid}  {block.splitlines()[0][4:]:<28} {block_name(block, new_blocks)}")
        for fid, block in old_blocks:
            if fid not in new:
                print(f"removed  {fid}  {block.splitlines()[0][4:]:<28} {block_name(block, old_blocks)}")
        return 0
    for fid, block in new_blocks:
        print(f"{fid}  {block.splitlines()[0][4:]:<28} {block_name(block, new_blocks)}")
    return 0


# ───────────────────────────── splice ─────────────────────────────

def cmd_splice(args):
    """
    Rebuild the file from the BASE revision, taking only the named blocks from the working copy:
    a block in both is replaced, a block only in the working copy is inserted where it sits there,
    a block only in the base is deleted. Everything else stays exactly as the base had it.
    """
    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    working = read(args.file)
    base = base_text(args.file, args.base)
    if newline_of(working) != newline_of(base):
        sys.exit("line endings differ between the working copy and the base; refusing to splice.")

    _, new_blocks = split_blocks(working)
    preamble, old_blocks = split_blocks(base)
    new = dict(new_blocks)
    old = dict(old_blocks)

    unknown = [i for i in ids if i not in new and i not in old]
    if unknown:
        sys.exit(f"fileID(s) in neither version: {', '.join(unknown)}")

    out = list(old_blocks)
    actions = []

    # Replace or delete in place.
    for i in ids:
        if i in old:
            index = next(k for k, (fid, _) in enumerate(out) if fid == i)
            if i in new:
                out[index] = (i, new[i])
                actions.append(f"replaced {i}")
            else:
                out.pop(index)
                actions.append(f"deleted  {i}")

    # Insert blocks the base never had, before the block that follows them in the working copy.
    order = [fid for fid, _ in new_blocks]
    for i in ids:
        if i in old or i not in new:
            continue
        pos = order.index(i)
        follower = next((fid for fid in order[pos + 1:] if any(fid == f for f, _ in out)), None)
        index = next((k for k, (fid, _) in enumerate(out) if fid == follower), len(out))
        out.insert(index, (i, new[i]))
        actions.append(f"inserted {i}" + (f" before {follower}" if follower else " at end"))

    result = preamble + "".join(block for _, block in out)
    for a in actions:
        print(a)
    if args.dry_run:
        print("dry run: nothing written.")
        return 0
    write(args.file, result)
    print(f"wrote {args.file}. Run `check` next, then reload the file in Unity WITHOUT saving the open copy.")
    return 0


# ───────────────────────────── remove-mod ─────────────────────────────

def cmd_remove_mod(args):
    text = read(args.file)
    nl = newline_of(text)
    pattern = re.compile(
        r"^    - target: \{fileID: %s, guid: %s, type: 3\}%s"
        r"      propertyPath: %s%s"
        r"      value: (?P<value>.*?)%s"
        r"      objectReference: \{fileID: (?P<ref>[^}]*)\}%s"
        % (re.escape(args.target), re.escape(args.guid), re.escape(nl), re.escape(args.prop), re.escape(nl),
           re.escape(nl), re.escape(nl)),
        re.M)
    matches = [m for m in pattern.finditer(text) if args.value is None or m.group("value") == args.value]
    if len(matches) != 1:
        found = [m.group("value") for m in pattern.finditer(text)]
        sys.exit(f"expected exactly one modification of {args.prop} on {args.target}; found {len(matches)}"
                 + (f" (values present: {found})" if found else "") + ". Nothing written.")
    m = matches[0]
    print(f"removing {args.prop} = {m.group('value')!r} on target {args.target}")
    if args.dry_run:
        print("dry run: nothing written.")
        return 0
    write(args.file, text[:m.start()] + text[m.end():])
    print(f"wrote {args.file}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="is the diff only what you meant, or did a save churn the file?")
    p.add_argument("file")
    p.add_argument("--base", default="HEAD")
    p.add_argument("--max-lines", type=int, default=80, help="changed lines above this are treated as churn")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("blocks", help="list YAML blocks, or with --changed the ones that differ from base")
    p.add_argument("file")
    p.add_argument("--changed", action="store_true")
    p.add_argument("--base", default="HEAD")
    p.set_defaults(func=cmd_blocks)

    p = sub.add_parser("splice", help="keep only the named blocks of the working copy, on top of base")
    p.add_argument("file")
    p.add_argument("--ids", required=True, help="comma-separated fileIDs (the &NNN after --- !u!)")
    p.add_argument("--base", default="HEAD")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_splice)

    p = sub.add_parser("remove-mod", help="delete one PrefabInstance modification entry")
    p.add_argument("file")
    p.add_argument("--target", required=True, help="the target fileID in the source prefab")
    p.add_argument("--guid", required=True, help="the source prefab's guid")
    p.add_argument("--prop", required=True, help="propertyPath, e.g. m_AnchorMin.y")
    p.add_argument("--value", help="only remove if the stored value is exactly this")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_remove_mod)

    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
