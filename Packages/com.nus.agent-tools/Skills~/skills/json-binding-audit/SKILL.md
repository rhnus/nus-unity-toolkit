---
name: json-binding-audit
description: Find authored JSON keys that no C# field reads. Use after editing any catalog under Assets/Resources or Assets/StreamingAssets, when an authored setting appears to have no effect, or when adding a new field to a data-model class.
---

# Audit JSON → C# binding

Newtonsoft and `JsonUtility` **ignore unknown members by default**. A key written at the wrong nesting
level parses cleanly, binds nothing, throws nothing, and logs nothing. The setting silently never takes
effect, and the file looks correct to every reader.

This is not hypothetical. A `durationModel` key sat one level too high in a task catalog — where no field
declares it — while the loader only read it from inside a nested `crashTuning` object. The game silently ran
the wrong model for a whole module. The authoring comment beside it described the intended result in
convincing detail, so it read as working code.

## Run it

```bash
python ${CLAUDE_SKILL_DIR}/scripts/json_binding_audit.py "Assets/Resources/*.json"
python ${CLAUDE_SKILL_DIR}/scripts/json_binding_audit.py Assets/Resources/task_catalog.json
```

Takes a few seconds for a typical set of catalogs. Exit code 0 when clean.

## Reading the output

**`MISPLACED`** — the key is declared in C#, but on a different class than the node it was authored on,
*and* the node's class holds that other class as a nested field. This is the actionable case and the fix
is usually to nest the key one level down:

```
MISPLACED  'durationModel' at $.modules[0]
           node reads as TaskCatalogModule, which has no such field;
           declared on CrashTuning, which TaskCatalogModule holds as a nested field
           -> nest the key there, or move the field up to TaskCatalogModule
```

**`UNKNOWN`** — no C# field of that name exists anywhere. Either a typo, or a setting someone authored
that was never implemented.

**`CHECK`** — weaker signal: declared on one or two unrelated classes. Verify by hand.

## Before acting on a finding

**Verify it, every time.** Grep for the key name across all of `Assets/` before concluding anything is
dead. A false `UNKNOWN` is the one outcome that could get working configuration deleted.

The audit is a heuristic: it infers each node's class by which class declares the most of its keys.
It will be wrong when a node has no model class at all, when binding goes through a custom
`JsonConverter` or manual `JObject` reads, or when `[JsonProperty("other_name")]` renames a field.

It scans all of `Assets/` by default for exactly this reason — an earlier version defaulted to
`Assets/Scripts` and reported every `advanceOn` key in a tutorial catalog as dead, when the field was
simply declared in a class under another top-level folder. Do not narrow `--models` unless you
have a specific reason.

## When adding a field to a catalog class

Author one JSON file that uses the new key, run the audit, and confirm it comes back clean. That closes
the loop that `durationModel` never had — a compile check cannot catch this, because both the JSON and
the C# are individually valid.
