---
name: unity-compile-check
description: Verify Unity C# compiles without closing the editor. Use after editing any .cs file under Assets/ or an embedded package, before reporting work as done, or whenever you need to know if code builds while Unity is open and holding the project lock.
---

# Verify a Unity compile while the editor is open

`Unity.exe -batchmode -quit` **cannot open a project the editor already has locked**. It exits with a
lock error, which reads like a build failure and is not one. Do not try it, and do not ask the user to
close the editor. Drive the editor's own Roslyn instead — it needs no lock.

## Run it

```bash
python "${CLAUDE_SKILL_DIR}/scripts/unity_compile_check.py"                        # Assembly-CSharp
python "${CLAUDE_SKILL_DIR}/scripts/unity_compile_check.py" --assembly editor      # Assembly-CSharp-Editor
python "${CLAUDE_SKILL_DIR}/scripts/unity_compile_check.py" --assembly MyGame.UI   # any asmdef, by its name
```

Runs from any directory inside the project. Exit code 0 means no real errors. Add `--show-warnings`
only when chasing a specific warning; most projects carry dozens of them and they are noise.

**Which assemblies exist:** every `.asmdef` under `Assets/` (and embedded packages) is its own assembly, named by
the asmdef's `name` field; code outside any asmdef is `Assembly-CSharp` (or `Assembly-CSharp-Editor` under an
`Editor` folder). A change inside an asmdef is NOT checked by a plain `runtime` run, so compile the assembly the
changed file belongs to:

```bash
grep -rH --include=*.asmdef '"name"' Assets Packages
```

Compiling a dependency first is what lets the assembly above it link against the code you just changed,
because the reference is repointed at the copy this script built. When a change spans a pair, run them in
dependency order: `runtime` then `editor`, or an asmdef before the assembly that references it. Skip the first and
the second links against Library's older copy, which reports a method you just added as missing.

## Reading the output

**`PASS - 0 errors`** — done. Do not re-run to be sure and do not open files to double-check.

**`FAIL - N error(s)`** — real breaks in your code, listed with file and line. Fix and re-run.

**`-- N error(s) from a STALE SOURCE LIST --`** — not your bug. The response file is rebuilt from the
assembly's `.csproj`, which Unity only regenerates when it reimports. A file created since the last
reimport is missing from it, so every reference to its types reports `CS0246: type could not be found`
for a type that plainly exists on disk. The script checks each one against `Assets/` and separates them
for you.

**`-- N new .cs file(s) NOT COMPILED --`**: those files were skipped, so PASS does not cover them.

If a stale-list error blocks something you genuinely need compiled, ask the user to focus the Unity
window so it reimports and regenerates the csproj. Never "fix" one by editing code.

## Which assembly a test belongs to

Getting this wrong produces a type-not-found error that looks exactly like a missing class. A test can only see
what its assembly references: a test under `Assets/**/Editor/` with no asmdef compiles into
`Assembly-CSharp-Editor`, which sees `Assembly-CSharp` but no asmdef that isn't auto-referenced. A test asmdef sees
only the assemblies listed in its `references`. Read the `.asmdef` before referencing across modules, and record the
project's own layout in its CLAUDE.md.

## Prerequisites

The editor must have compiled the project at least once, so `Library/Bee/artifacts/*.dag/*.rsp` and the
`.csproj` files exist. On a fresh clone, open the project in Unity first.

## What compiling does not tell you

A clean compile says nothing about whether serialized fields are wired, whether an authored JSON key is
actually read, or whether a UnityEvent has a listener. Those fail silently at runtime. For the first,
use `unity-wiring-diagnose`; for the second, `json-binding-audit`.
