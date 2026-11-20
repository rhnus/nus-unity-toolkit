"""Scan Unity C# for motion and feedback smells, as a starting point for a polish audit.

    python motion_scan.py <file-or-folder> [<file-or-folder> ...] [--detail] [--json]

Colour literals and direct scale writes are common and mostly harmless, so they are summarised per file unless
--detail lists every line.

Each hit is a lead, not a verdict: confirm it in context before it goes into an audit (SKILL.md, step 3).
Standard library only; reads .cs files and nothing else.
"""
import json
import os
import re
import sys

# rule id -> (title, what to check before calling it a finding)
RULES = {
    "scaled-time": ("Scaled time in UI motion",
                    "Only a problem if something sets Time.timeScale to 0; search for writes to it first."),
    "yield-alloc": ("New yield object in a coroutine",
                    "Costs only inside a loop that runs every frame; then cache it (static readonly)."),
    "frame-search": ("Scene search or GetComponent in a per-frame method",
                     "Fine if guarded to run once; a cost on every frame otherwise."),
    "frame-alloc": ("Allocation in a per-frame method",
                    "new List / LINQ / string building inside Update allocates every frame."),
    "base-skipped": ("Override of a shared input handler without a base call",
                     "Check what the base does (sounds, eased return, feedback hooks) and whether anything here needs it."),
    "colour-literal": ("Hard-coded colour",
                       "Verdict, attention and state colours should come from the project's theme tokens."),
    "direct-scale": ("Scale written directly",
                     "Hover and press scaling belongs to the shared feedback component, not hand-written code."),
    "instant-show": ("Panel shown with an instant SetActive(true)",
                     "Fine for a panel that fades itself in on enable; a pop-in otherwise."),
}

FRAME_METHODS = re.compile(r"\bvoid\s+(Update|LateUpdate|FixedUpdate|OnGUI)\s*\(")
INPUT_OVERRIDE = re.compile(
    r"\boverride\s+void\s+(OnBeginDrag|OnDrag|OnEndDrag|OnDrop|OnPointerEnter|OnPointerExit|OnPointerDown|OnPointerUp|OnPointerClick)\s*\(")
SEARCH = re.compile(r"\b(GameObject\.Find\w*|Find(Any|First)?ObjectsOfType|Find(Any|First)ObjectByType|FindObjectsByType|GetComponents?(InChildren|InParent)?\s*<)")
ALLOC = re.compile(r"\bnew\s+(List|Dictionary|HashSet)\s*<|\.(Where|Select|ToList|ToArray|OrderBy)\s*\(|string\.Format\s*\(|\$\"")
SCALED = re.compile(r"\bTime\.(deltaTime|time)\b")
YIELD_NEW = re.compile(r"yield\s+return\s+new\s+(WaitForEndOfFrame|WaitForSeconds|WaitForFixedUpdate)\s*\(")
COLOUR = re.compile(r"\bnew\s+Color(32)?\s*\(\s*[\d.]")
SCALE_SET = re.compile(r"\.localScale\s*=")
SHOW = re.compile(r"(\w*(Panel|Popup|Window|Modal|Overlay|Dialog)\w*)\s*(\.gameObject)?\s*\.SetActive\s*\(\s*true\s*\)", re.I)


def method_bodies(lines, header):
    """Yield (start, end) line ranges, 0-based inclusive, of methods whose header matches."""
    i = 0
    while i < len(lines):
        if header.search(lines[i]):
            depth, opened, j = 0, False, i
            while j < len(lines):
                code = strip_comment(lines[j])
                depth += code.count("{") - code.count("}")
                opened = opened or "{" in code
                if opened and depth <= 0:
                    break
                j += 1
            yield i, j
            i = j + 1
        else:
            i += 1


def strip_comment(line):
    cut = line.find("//")
    return line if cut < 0 else line[:cut]


def scan_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    hits = []

    def add(rule, n):
        hits.append({"rule": rule, "file": path, "line": n + 1, "code": lines[n].strip()[:140]})

    frame_lines = set()
    for start, end in method_bodies(lines, FRAME_METHODS):
        frame_lines.update(range(start, end + 1))

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
        if YIELD_NEW.search(code):
            add("yield-alloc", n)
        if COLOUR.search(code):
            add("colour-literal", n)
        if SCALE_SET.search(code):
            add("direct-scale", n)
        if SHOW.search(code):
            add("instant-show", n)
        if n in frame_lines:
            if SEARCH.search(code):
                add("frame-search", n)
            if ALLOC.search(code):
                add("frame-alloc", n)
    return hits


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


SUMMARISED = ("colour-literal", "direct-scale")


def main(argv):
    as_json = "--json" in argv
    detail = "--detail" in argv
    targets = [a for a in argv if a not in ("--json", "--detail")]
    if not targets:
        print(__doc__.strip())
        return 2
    hits = []
    for target in targets:
        if not os.path.exists(target):
            print(f"Not found: {target}", file=sys.stderr)
            return 2
        for path in sorted(cs_files(target)):
            hits.extend(scan_file(path))

    if as_json:
        print(json.dumps(hits, indent=2))
        return 0

    if not hits:
        print("No motion smells found.")
        return 0
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
