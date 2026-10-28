"""
Find CONTENT living inside a Unity scene: the things that force a scene edit (and a scene merge conflict)
every time someone changes copy, a question, or a data value.

    python scene_content_audit.py Assets/Scenes/Main.unity
    python scene_content_audit.py Assets/Scenes/Main.unity --top 20 --min-words 6

Reports, most actionable first:
  INDEX   UnityEvent calls that pick content by list position (ShowQuiz(3), PlayLine(7)). Adding an item
          above it silently shows the wrong thing.
  PROSE   UnityEvent string arguments that are sentences, not ids. Copy belongs in data.
  COPY    Text typed into scene-owned objects: TMP/Text m_text and other prose fields on objects that are
          not prefab instances. Each one is a scene edit when the wording changes.
  HOLDER  Scene-owned components carrying a lot of authored prose: candidates to become a prefab or a
          data asset, so their content changes stop touching the scene.

Each finding is a candidate, not a verdict: an id that happens to contain spaces is fine.
"""

import argparse
import re
import sys
from collections import Counter, defaultdict

HEADER = re.compile(r"^--- !u!(\d+) &(-?\d+)( stripped)?", re.M)
STEP_NAME = re.compile(r"^ *- name: (.+)$")
CONTENT_METHOD = re.compile(r"show|play|select|open|start|load|display|set(quiz|question|line|page|step)", re.I)


def blocks(text):
    starts = [m for m in HEADER.finditer(text)]
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        yield m.group(1), m.group(2), bool(m.group(3)), text[m.start():end]


def words(s):
    # Two letters or more, so spaced-out display text ("D A S H B O A R D") is not mistaken for a sentence.
    return len(re.findall(r"[A-Za-z'][A-Za-z']+", s))


def object_names(text):
    """fileID of each GameObject -> its m_Name, so findings can say where they are."""
    names = {}
    for cls, fid, stripped, body in blocks(text):
        if cls == "1":
            m = re.search(r"^  m_Name: (.*)$", body, re.M)
            if m:
                names[fid] = m.group(1).strip()
    return names


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scene")
    p.add_argument("--top", type=int, default=12, help="examples shown per category")
    p.add_argument("--min-words", type=int, default=5, help="words before a string counts as prose")
    args = p.parse_args()

    with open(args.scene, encoding="utf-8", errors="ignore") as handle:
        text = handle.read()
    names = object_names(text)

    index_calls, prose_args = [], []
    copy_fields, holders = [], Counter()
    holder_examples = defaultdict(list)

    for cls, fid, stripped, body in blocks(text):
        if cls != "114" or stripped:
            continue
        go = re.search(r"m_GameObject: \{fileID: (-?\d+)\}", body)
        owner = names.get(go.group(1), f"fileID {go.group(1)}") if go else "?"
        script = re.search(r"m_EditorClassIdentifier: [^:]*::(\S+)", body)
        comp = script.group(1).split(".")[-1] if script else "MonoBehaviour"

        # UnityEvent persistent calls, remembering the nearest step/list-entry name above each.
        step = None
        lines = body.splitlines()
        for i, line in enumerate(lines):
            sm = STEP_NAME.match(line)
            if sm:
                step = sm.group(1).strip()
            if "m_MethodName:" not in line:
                continue
            method = line.split("m_MethodName:", 1)[1].strip()
            window = "\n".join(lines[i:i + 10])
            mode = re.search(r"m_Mode: (\d)", window)
            mode = mode.group(1) if mode else ""
            where = f"{owner} / {step}" if step else owner
            if mode == "3" and CONTENT_METHOD.search(method):
                arg = re.search(r"m_IntArgument: (-?\d+)", window)
                index_calls.append(f"{where}: {method}({arg.group(1) if arg else '?'})")
            if mode == "5":
                arg = re.search(r"m_StringArgument: (.*)", window)
                value = arg.group(1).strip() if arg else ""
                if words(value) >= args.min_words and " " in value:
                    prose_args.append(f"{where}: {method}(\"{value[:70]}{'...' if len(value) > 70 else ''}\")")

        # Authored prose stored on this scene-owned component.
        prose = 0
        for m in re.finditer(r"^ {2,}(m_text|[A-Za-z_]+): (.+)$", body, re.M):
            key, value = m.group(1), m.group(2).strip().strip("'\"")
            if key.startswith("m_") and key != "m_text":
                continue
            if words(value) >= args.min_words and " " in value and not value.startswith("{"):
                prose += 1
                if len(holder_examples[(owner, comp)]) < 2:
                    holder_examples[(owner, comp)].append(f"{key}: {value[:60]}{'...' if len(value) > 60 else ''}")
                if key == "m_text":
                    copy_fields.append(f"{owner} ({comp}): \"{value[:70]}{'...' if len(value) > 70 else ''}\"")
        if prose:
            holders[(owner, comp)] += prose

    def section(title, items, advice):
        print(f"\n{title}: {len(items)}")
        if items:
            print(f"  {advice}")
        for item in items[:args.top]:
            print(f"   - {item}")
        if len(items) > args.top:
            print(f"   ... and {len(items) - args.top} more")

    print(f"Content audit of {args.scene}")
    section("INDEX  content picked by list position", index_calls,
            "Pick by a stable id instead (a quiz id, a step-id tag in the data), or the content moves when the list changes.")
    section("PROSE  sentences passed as event arguments", prose_args,
            "Move the sentence to the data file and pass its id.")
    section("COPY   UI text typed into scene-owned objects", copy_fields,
            "Placeholder copy shows whenever a code path forgets to set it. Set it from data, or make the object a prefab.")
    ranked = [f"{owner} ({comp}): {n} prose field(s), e.g. {'; '.join(holder_examples[(owner, comp)])}"
              for (owner, comp), n in holders.most_common() if n >= 3]
    section("HOLDER scene-owned components carrying 3+ prose fields", ranked,
            "Make the object a prefab instance (content then lives in the .prefab) or move the content to a data asset.")


if __name__ == "__main__":
    main()
