---
name: keep-content-out-of-scenes
description: Design a Unity feature so content (copy, which question or line a step shows, per-outcome variants, panel figures and labels) lives in data or prefabs instead of in the scene, so changing it never needs a scene edit or a scene merge. Use when a content change would mean editing a .unity file, when teammates keep conflicting on the same scene, when a step picks content by list position, when choosing how to wire a new step, quiz or dialogue, or to audit a scene for content that should move out.
---

# Keep content out of scenes

A scene is the worst place to keep anything that changes often. It's one huge file several people edit,
Unity rewrites unrelated parts of it on save, and a merge conflict in it can't be resolved by hand. Every
line of copy, every "show question #3" and every label typed into a scene object becomes a scene edit the
next time someone changes it.

The goal: **the scene holds wiring that rarely changes; data files and prefabs hold the content.** Then a
content change is a small diff in a file that merges normally.

## 1. Find what's in the scene now

```bash
python ${CLAUDE_SKILL_DIR}/scripts/scene_content_audit.py Assets/Scenes/<Scene>.unity
```

| Category | Meaning | Usual fix |
|---|---|---|
| **INDEX** | An event picks content by list position: `ShowQuiz(3)`, `StartDialogueGroupNPC(7)` | Pattern A or B |
| **PROSE** | A sentence passed as an event argument: `set_text("Drag each card...")` | Pattern A, passing an id instead of the sentence |
| **COPY** | UI text typed into a scene-owned object | Pattern E, or make the object a prefab |
| **HOLDER** | A scene-owned component carrying lots of authored prose or figures | Pattern D |

Findings are candidates. A sentence that will never change can stay. Fix the ones that change often, or
that someone is about to change.

## 2. Patterns

**A. Pick by stable id, never by position.** Replace `Show(int index)` with `ShowById(string id)`, looked up
in the data file. An index silently shows the wrong item when anyone inserts one above it, and the
mistake only appears in play. A missing id should log an error naming the id, so the gap is visible.

**B. Let the data claim the step.** Keep the scene's generic call (`ShowQuiz(0)`, `StartGrouping("X")`) and
tag the content in data with the step's stable id (`"SequenceStepId": "<step GUID>"`). At runtime the code
looks for content tagged with the running step and uses it, falling back to the old behaviour when none is
tagged. Re-pointing a step is then a data edit. Use the step's **stable GUID**, not its display name (names
get edited), and keep it distinct from any content or analytics id the project already has.

**C. Variants by a flag in data, not by wiring.** When a line or panel differs by outcome (under budget /
over, passed / failed), put a flag on the base entry (`"variantsBy": "costOutcome"`) and have the playing
code pick `<base>_<Variant>` when it exists. Steps keep one plain call, and adding a variant is a data
edit. Without the flag, every outcome-aware step needs re-wiring to a special component.

**D. Content-bearing objects become prefab instances.** A scene object whose job is to hold content (a
data source with titles, tiles and labels; a panel's copy) should be an instance of a prefab. Its fields
then live in the `.prefab`, which changes on its own. Converting is a one-time scene change: do it in
Unity, then keep only that change with `unity-scene-safe-edit` (`splice`). Component fileIDs survive the
conversion, so events that point at them keep working.

**E. Every displayed string is set from data, with a safe default.** A label whose authored text is a
placeholder ("Calculate following metrics For Week 17") shows it whenever a code path forgets to set it.
Set the text when the screen opens, from data. Also set a correct default as soon as the component loads
(in `Awake`), so no path can show the placeholder. Build titles from data (`"Week {0} Check-in"` from the
week number) rather than typing them per screen.

## 3. The trade-off, and how to pay for it

Patterns B and C move a decision out of the place people look. Someone reading the scene sees
`ShowQuiz(0)` and doesn't know data overrides it. Pay for that every time:

- **Test the routing**: a test that the tagged item wins, that an untagged step falls back, and that the
  shipped data still carries the tag. A broken route should turn a test red, not ship.
- **Write it down where the wiring is**: a code comment on the routing method, and a line in the team's
  scene-change notes ("step X is routed by tag in QuizData.json").
- **Log on a miss**: an id or tag that matches nothing logs an error naming it, instead of failing silently.

## 4. Doing a migration

1. Run the audit and pick the items that change most or that someone is about to change.
2. Choose the pattern, and add the runtime support (lookup by id, tag routing, variant flag) with tests.
3. Move the content into the data file or prefab.
4. Make the scene change once, if one is needed (pattern A changes the call; B and C usually need none),
   following `unity-scene-safe-edit`.
5. Re-run the audit, and record what moved where.

## Done means

- Changing the content touches only data files or prefabs, never the scene.
- The routing has tests, and a miss logs an error naming the id.
- Anyone reading the scene can find where the content comes from (code comment, notes).
