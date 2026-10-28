"""
Find authored JSON keys that no C# field will ever read.

Newtonsoft (and JsonUtility) ignore unknown members by default, so a key written at the wrong nesting
level parses cleanly, loads nothing, and reports nothing. The setting simply never takes effect. That is
how a `durationModel` key sat one level too high -- where no field declares it -- while the loader only
read it from inside `crashTuning`, so the setting it carried never ran.

    python json_binding_audit.py Assets/Resources/some_catalog.json
    python json_binding_audit.py Assets/Resources/*.json --models Assets/Scripts/DataModels

Reports two kinds of finding:
  MISPLACED  the key IS declared in C#, but on a different class than the node it was authored on
  UNKNOWN    the key is declared nowhere -- a typo, or a setting that was never implemented

Exit code 0 when nothing is found.
"""

import argparse
import glob
import json
import os
import re
import sys

# `_note` / `_xxx_comment` keys are the house convention for authoring documentation. They are meant to
# be unread, so flagging them would bury every real finding.
COMMENT_KEY = re.compile(r"^_")

FIELD = re.compile(
    r"public\s+(?:static\s+|readonly\s+)*"
    r"(?P<type>[A-Za-z_][\w\.<>\[\],\s\?]*?)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:=[^;]*)?;"
)
PROPERTY = re.compile(
    r"public\s+(?:static\s+)?(?P<type>[A-Za-z_][\w\.<>\[\],\s\?]*?)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:=>|\{\s*get)"
)
CLASS = re.compile(r"\b(?:class|struct)\s+(?P<name>[A-Za-z_]\w*)")


def class_bodies(text):
    """Yield (class_name, body) by brace-matching from each class declaration."""
    for match in CLASS.finditer(text):
        brace = text.find("{", match.end())
        if brace < 0:
            continue
        depth, index = 0, brace
        while index < len(text):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        yield match.group("name"), text[brace:index]


def scan_models(paths):
    """{class_name: {field_name: type}} for every class found under the given roots."""
    models = {}
    for root in paths:
        walk = [root] if os.path.isfile(root) else []
        if not walk:
            for folder, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d not in (".git", "obj", "bin")]
                walk += [os.path.join(folder, f) for f in files if f.endswith(".cs")]
        for path in walk:
            try:
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    text = handle.read()
            except OSError:
                continue
            text = re.sub(r"//[^\n]*", "", text)
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            for name, body in class_bodies(text):
                fields = models.setdefault(name, {})
                for pattern in (FIELD, PROPERTY):
                    for hit in pattern.finditer(body):
                        if hit.group("type").strip() in ("return", "new"):
                            continue
                        fields.setdefault(hit.group("name"), hit.group("type").strip())
    return models


def declaring(models, key):
    """Classes declaring a field named `key`, matched case-insensitively as Newtonsoft binds."""
    low = key.lower()
    return [c for c, f in models.items() if any(n.lower() == low for n in f)]


def owner_of(models, keys):
    """The class that best explains this node: the one declaring the most of its keys."""
    best, score = None, 0
    for name, fields in models.items():
        low = {n.lower() for n in fields}
        hit = sum(1 for k in keys if k.lower() in low)
        if hit > score:
            best, score = name, hit
    return best, score


def walk_json(node, models, path="$", findings=None):
    findings = [] if findings is None else findings

    if isinstance(node, list):
        for index, item in enumerate(node):
            walk_json(item, models, f"{path}[{index}]", findings)
        return findings

    if not isinstance(node, dict):
        return findings

    keys = [k for k in node if not COMMENT_KEY.match(k)]
    if keys:
        owner, score = owner_of(models, keys)
        # Below half coverage the node probably has no model class at all (free-form data, a dictionary,
        # a localisation blob). Guessing an owner there produces noise, so say nothing.
        if owner and score >= max(2, len(keys) / 2):
            # "Strong" = the class explains most of the node, so naming it in the report is fair.
            strong = score >= max(2, len(keys) * 0.6)
            owned = {n.lower() for n in models[owner]}
            for key in keys:
                if key.lower() in owned:
                    continue
                elsewhere = [c for c in declaring(models, key) if c != owner]
                if not elsewhere:
                    findings.append(("UNKNOWN", path, key, owner if strong else None, []))
                    continue

                # Only the nested case is actionable: the key belongs to a class the owner already holds
                # as a field, so "move it one level down" is a concrete fix. A common field name declared
                # on a dozen unrelated classes says nothing, so stay quiet rather than cry wolf.
                nested = [c for c in elsewhere if c in {v.strip("?[] ") for v in models[owner].values()}]
                if nested:
                    findings.append(("MISPLACED", path, key, owner, nested))
                elif len(elsewhere) <= 2 and strong:
                    findings.append(("CHECK", path, key, owner, elsewhere))

    for key, value in node.items():
        if not COMMENT_KEY.match(key):
            walk_json(value, models, f"{path}.{key}", findings)
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("json", nargs="+", help="authored JSON file(s); globs allowed")
    # Defaults to ALL of Assets/: model classes are not confined to Scripts/, and a root that misses one
    # reports its keys as dead -- the one failure mode that could get working configuration deleted.
    parser.add_argument("--models", nargs="*", default=["Assets"],
                        help="roots to scan for C# model classes (default: Assets)")
    args = parser.parse_args()

    models = scan_models(args.models)
    print(f"scanned {len(models)} C# classes from {', '.join(args.models)}")

    targets = []
    for pattern in args.json:
        targets += sorted(glob.glob(pattern)) or ([pattern] if os.path.isfile(pattern) else [])
    if not targets:
        sys.exit("no JSON files matched")

    total = 0
    for path in targets:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"\n{path}\n  SKIPPED - {exc}")
            continue

        findings = walk_json(data, models)
        if not findings:
            print(f"\n{path}\n  clean")
            continue

        total += len(findings)
        print(f"\n{path}")
        for kind, where, key, owner, elsewhere in findings:
            if kind == "MISPLACED":
                print(f"  MISPLACED  '{key}' at {where}")
                print(f"             node reads as {owner}, which has no such field;")
                print(f"             declared on {', '.join(elsewhere)}, which {owner} holds as a nested field")
                print(f"             -> nest the key there, or move the field up to {owner}")
            elif kind == "CHECK":
                print(f"  CHECK      '{key}' at {where}  (node reads as {owner}; declared only on {', '.join(elsewhere)})")
            else:
                seen = f"; node reads as {owner}" if owner else ""
                print(f"  UNKNOWN    '{key}' at {where}  (no C# field of this name anywhere{seen})")

    print(f"\n{total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
