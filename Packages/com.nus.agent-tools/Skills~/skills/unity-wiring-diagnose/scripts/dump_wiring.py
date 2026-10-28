"""
Show how a component is ACTUALLY wired in a prefab or scene.

The Inspector is not available here, and a serialized field's real value is regularly the opposite of
what the code implies: fields sitting at 0 because Unity zero-filled them when they were added, enum
fields all reading 0 because nobody set them, object references pointing at {fileID: 0} because the slot
was never filled. Every one of those looks like a code bug and is not.

    python dump_wiring.py MetricsManager                       # every prefab/scene using it
    python dump_wiring.py ChartScaler --file Assets/Prefabs/X.prefab
    python dump_wiring.py SummaryPanel --field showTotals

Prints each instance's owning GameObject, its serialized fields, and flags unwired references.
"""

import argparse
import glob
import os
import re
import sys

ANCHOR = re.compile(r"^---\s+!u!(?P<class>\d+)\s+&(?P<anchor>\d+)")
FILEID = re.compile(r"\{fileID:\s*(-?\d+)")

# Unity's own bookkeeping. Useful occasionally, but it buries the authored fields you came to read.
NOISE = {
    "m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance", "m_PrefabAsset",
    "m_EditorHideFlags", "m_EditorClassIdentifier", "m_Script", "m_Name",
}


def script_guid(name):
    """guid of <name>.cs from its .meta, which is how MonoBehaviour blocks identify their script."""
    hits = [p for p in glob.glob(f"Assets/**/{name}.cs.meta", recursive=True)]
    if not hits:
        sys.exit(f"no Assets/**/{name}.cs.meta -- check the spelling of the component name")
    with open(hits[0], encoding="utf-8", errors="ignore") as handle:
        match = re.search(r"guid:\s*([0-9a-f]{32})", handle.read())
    if not match:
        sys.exit(f"no guid in {hits[0]}")
    return match.group(1), hits[0][: -len(".meta")]


def documents(path):
    """Split a Unity YAML asset into [(class_id, anchor, [lines])]."""
    docs, current = [], None
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            match = ANCHOR.match(line)
            if match:
                if current:
                    docs.append(current)
                current = (match.group("class"), match.group("anchor"), [])
            elif current:
                current[2].append(line.rstrip("\n"))
    if current:
        docs.append(current)
    return docs


def names_by_anchor(docs):
    """{anchor: GameObject name} so component blocks can say which object they sit on."""
    names = {}
    for class_id, anchor, lines in docs:
        if class_id != "1":                       # 1 = GameObject
            continue
        for line in lines:
            hit = re.match(r"\s*m_Name:\s*(.+)$", line)
            if hit:
                names[anchor] = hit.group(1).strip()
                break
    return names


def report(path, guid, field_filter, show_noise):
    docs = documents(path)
    names = names_by_anchor(docs)
    found = 0

    for class_id, anchor, lines in docs:
        if class_id != "114" or not any(guid in l for l in lines):   # 114 = MonoBehaviour
            continue
        found += 1

        owner = "?"
        for line in lines:
            hit = re.match(r"\s*m_GameObject:.*fileID:\s*(-?\d+)", line)
            if hit:
                owner = names.get(hit.group(1), f"fileID {hit.group(1)}")
                break

        print(f"\n  {os.path.basename(path)}  ->  GameObject '{owner}'  (component anchor {anchor})")

        for line in lines:
            hit = re.match(r"\s{2}(\w+):\s*(.*)$", line)
            if not hit:
                continue
            key, value = hit.group(1), hit.group(2).strip()
            if key in NOISE and not show_noise:
                continue
            if field_filter and field_filter.lower() not in key.lower():
                continue

            note = ""
            ids = FILEID.findall(value)
            if ids and all(i == "0" for i in ids):
                note = "   <-- UNWIRED (fileID: 0)"
            elif value in ("0", "") and not ids:
                note = "   <-- zero/empty (check this is intended, not a zero-filled new field)"

            print(f"      {key}: {value}{note}")

    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("component", help="C# component name, e.g. MetricsManager")
    parser.add_argument("--file", nargs="*", help="specific .prefab/.unity/.asset files (default: search all)")
    parser.add_argument("--field", help="only show fields whose name contains this")
    parser.add_argument("--show-noise", action="store_true", help="include Unity bookkeeping fields")
    args = parser.parse_args()

    guid, source = script_guid(args.component)
    print(f"{args.component}  guid {guid}")
    print(f"declared in {source}")

    targets = args.file
    if not targets:
        targets = []
        for pattern in ("Assets/**/*.prefab", "Assets/**/*.unity", "Assets/**/*.asset"):
            targets += glob.glob(pattern, recursive=True)

    total, files = 0, 0
    for path in targets:
        try:
            with open(path, encoding="utf-8", errors="ignore") as handle:
                if guid not in handle.read():
                    continue
        except OSError:
            continue
        files += 1
        total += report(path, guid, args.field, args.show_noise)

    print(f"\n{total} instance(s) across {files} file(s)")
    if not total:
        print("  Nothing uses this component. If you expected wiring, the reference may be assigned")
        print("  at runtime instead, or the object may live in a scene not searched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
