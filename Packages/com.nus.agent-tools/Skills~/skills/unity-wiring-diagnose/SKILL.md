---
name: unity-wiring-diagnose
description: Diagnose Unity UI and component problems by reading prefab/scene YAML before changing code. Use when something does not appear, a serialized value seems ignored, an event does not fire, or before renaming or changing how a serialized field is accessed.
---

# Diagnose from the asset, not from the code

When a Unity thing does not work, the cause is in the `.prefab` / `.unity` / `.asset` far more often than
in the `.cs`. **Read the wiring before you change code.** Code that looks wrong is regularly compensating
for something non-obvious, and a "fix" applied without reading the asset usually breaks a second thing.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/dump_wiring.py MetricsManager
python ${CLAUDE_SKILL_DIR}/scripts/dump_wiring.py ChartScaler --field model
python ${CLAUDE_SKILL_DIR}/scripts/dump_wiring.py MyThing --file Assets/Prefabs/X.prefab
```

It prints each instance's owning GameObject and serialized fields, flagging `{fileID: 0}` as **UNWIRED**
and bare zeros as worth checking. GameObject names inside nested prefab instances sometimes resolve to a
raw fileID — that is a display limitation, not a finding.

## The trap that has cost the most time

**Unity zero-fills newly-added serialized fields with `default(T)`, ignoring the C# initializer.**

```csharp
[SerializeField] float cardHeight = 120f;   // existing prefabs get 0, not 120
```

Any asset serialized before the field existed keeps `default(T)` forever. This has caused a UI to be
invisible (every layout dimension 0), and a set of `ChartScaler`s to all behave as one model (`model: 0`
on every instance). Symptoms look exactly like broken code.

When a value "isn't being applied", dump the asset **first** and confirm what is actually stored. New
fields whose correct default is non-zero need setting on every existing asset, or a migration in
`OnValidate`/`Reset`.

Note the flip side: a new `bool` whose intended default is `false` is served correctly by zero-fill and
needs no re-authoring, so it is safe to add without touching any asset.

## Before renaming a serialized field

Renaming breaks every asset silently — the old value is dropped, the new name gets `default(T)`.

1. Confirm the old name by reading the `.prefab`/`.asset`.
2. Add `[FormerlySerializedAs("oldName")]`.
3. For a renamed nested `[Serializable]` class, matching is structural — verify by dumping the asset.

## What to look for

- **Enums serialize as ints.** `model: 0` is the first enum member. An enum field that was never set
  reads as the first member, not as "unset".
- **Masks serialize as ints.** Check the specific bit, not the number. A mask of `360` lacking bit 16
  is why a section never showed.
- **`{fileID: 0}`** means the slot is empty. If code does `GetComponent` where a serialized reference
  exists, the reference may point at a *sibling* component rather than `this` — check before "fixing".
- **`m_Enabled: 0`** on the component, or an inactive ancestor: `activeSelf` is this object only,
  `activeInHierarchy` includes every parent. A child cannot be active under an inactive parent.
- **Nested Canvas**: inherits the parent's render mode, ignores `sortingOrder` unless `overrideSorting`
  is set, and has its RectTransform driven by the parent layout. A panel with no Canvas of its own
  cannot sort above its siblings.
- **UnityEvent listeners** live in `m_PersistentCalls`. An empty list means nothing is wired, however
  correct the code is.

## Order of investigation

Cheapest first. Most of these bugs are found in step 1 or 2:

1. Dump the component's wiring. Is the field set? Is the reference non-zero?
2. Is the object and every ancestor active, and the component enabled?
3. Is the value what the code expects — right enum member, right bit, right layer?
4. Only then read the code.

When a bug has several plausible causes, expect them to be **stacked**. One invisible-UI case had four:
a mask missing a bit, a dead code path, zero-filled layout fields, and a busy-guard evaluated before the
wiring ran. Each masked the next, so fixing one changed nothing visible. Fix one at a time and re-check.

## After changing code

- **Trace every caller** of a modified method, especially event-callback ordering and cancellation paths.
- Confirm every new method has a caller and every new event has a subscriber.
- **Call out explicitly any prefab or Inspector reference a human must wire**, since you cannot.
- Verify it compiles with `unity-compile-check`. A clean compile does not mean it is wired.
