---
name: polish-a-transition
description: Audit and polish how a Unity UGUI activity moves and responds — how it opens, reveals its content, reacts to hover, pick, drag and drop, grades right and wrong, debriefs and closes — against one shared motion vocabulary, so every activity in a game feels like the same game. Use when asked to polish, smooth, juice or refine an activity's transitions or animation, when something "snaps", "feels janky", "pops in", flashes and stays stuck, or scrolls away while the player is reading, when comparing how activities feel, when adding a new interactive activity, or to audit one beat (say, wrong-answer feedback) across every activity. Plans first; changes nothing until the plan is approved.
---

# Polish a transition

Players judge a game's quality by its transitions more than by its features. A card that snaps into place, a
panel that pops in, a flash that leaves a bar stuck in the wrong colour, a view that scrolls away while the
player is reading: none of these is a bug a test catches, and each makes the game feel unfinished.

This skill turns "it feels janky" into a list a reviewer can tick, and keeps activities consistent by
measuring them all against **one motion vocabulary**: the same treatment for the same beat everywhere.

## Three modes

| Mode | Asked as | Output |
|---|---|---|
| **Audit an activity** | "polish the network diagram", "why does the sort feel janky" | Gap table for every beat of that activity |
| **Audit a beat** | "how does every activity show a wrong answer" | One row per activity for that beat |
| **Apply a plan** | "go ahead with the fixes for X" | The approved fixes, verified |

Audits change nothing. Apply only from a plan the person approved.

## The beats

Every interactive activity passes through the same moments. Audit them in this order:

1. **Enter**: the panel or window appears.
2. **Reveal**: its content (cards, nodes, rows, options) first appears.
3. **Hover**: the pointer rests on something usable.
4. **Pick**: something is grabbed or selected.
5. **Drag**: it moves with the pointer.
6. **Drop**: it lands, snaps, links or returns.
7. **Submit**: the answer is committed (the button's gate, any confirmation).
8. **Verdict**: right and wrong are shown.
9. **Attention**: the game points the player at something (a changed item, a hint, an event's subject).
10. **Debrief**: the lesson plays and the way on appears.
11. **Exit**: the activity is put away and the next one takes over.

## 1. Read the house vocabulary first

The project's motion values are the house style: hover and press scales, durations, easing, the attention
colour, the verdict colours. Find them before judging anything. Look in the project's CLAUDE.md for a pointer
(usually an interaction or motion doc). If the project has none, say so, propose one as part of the plan
(`references/audit-template.md` has a starter), and audit against the defaults in `references/checklist.md`.

Never invent a new value for one activity. A new treatment goes into the vocabulary first, then into the
activity.

A vocabulary row may still be undecided. Score that beat against the values already in use elsewhere in the
game, mark the verdict **Open**, and leave the fix as "waits on the vocabulary decision". Don't pick a value
for the project.

## 2. Map the activity's beats

**Scope it by prefab.** One folder often holds several activities, so start from what the player sees: the
activity's window prefab, the prefabs it spawns (cards, nodes, bars, cells) and its result panel. Find them
from the step that opens the activity, or by searching prefabs for the activity's main script.

Run the scanner on those prefabs. It scans exactly the scripts they use, plus the prefabs themselves, which
hold half the motion wiring: two feedback components fighting over one object, buttons and panels shown by
inspector `SetActive` events, and the feedback values in use. In the scripts it finds scaled time, new yields
in coroutine loops, searches and allocations in per-frame code (`Update`, `OnDrag`, coroutine loops), input
overrides that skip their base call, hard-coded colours, direct scale writes and panels popped in with
`SetActive(true)`.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/motion_scan.py "<window>.prefab" "<card>.prefab" [...]
```

A folder or a `.cs` file works too. Every hit is a lead, not a finding.

**An activity in parts** (a staged build, a second round, a part that unlocks after a dialogue) gets its beats
mapped per part, plus one more beat for each **hand-over** between parts: what changes on screen, and whether
it eases or snaps. Hand-overs are where activities most often break.

Then, for each beat, record what happens today with `file:line` evidence: instant or animated, what drives it (coroutine, `Update` lerp, Animator, a feedback component, a
CanvasGroup fade), and whether it runs in unscaled time. Read the activity's prefab as well as its scripts:
feedback components are often wired in the prefab, not called from code. For a large activity, hand this to a
read-only subagent with `references/survey-brief.md` and the scanner's output.

Where the editor is available, watch it too. A capture of each beat (or a short recording) catches what code
reading misses: a flash nobody sees because something covers it, a reveal too fast to register, two
animations fighting. Mid-transition stills need the game advanced a frame at a time. When the editor isn't
available, say so in the audit and list the captures that would settle what code reading couldn't.

## 3. Score each beat

Run `references/checklist.md` for each beat, then the engineering checks at its end. A beat fails when it is
missing, inconsistent with the vocabulary, or broken (stuck colour, view jump, double animation, dead input
during motion). `references/insights.md` holds the rules learned the hard way; check the activity against
every one that applies.

**Check a claim before it becomes a finding.** Code reading, yours or a subagent's, overstates breakage. Before
a row says **Broken**, confirm the path that reaches it and look for what may already cover it:

- a cleanup that runs anyway (`OnDestroy`, a pool that rebuilds, a teardown the caller does);
- a base class or a sibling component doing the work the override seems to drop;
- a flag or field that nothing reads for this activity;
- a condition the game never meets (a time scale nothing sets to 0, a mode never entered).

What survives is **Broken**; what is real but unreachable today is **Latent**; what you couldn't trace is
**Unconfirmed**, with what would settle it.

## 4. Write the plan

Fill `references/audit-template.md`: one row per beat, its verdict, the fix and its size. Prefer, in order:

1. **Wiring an existing shared component** (a hover feedback recipe, a fade-in-on-enable, an attention
   pulse). No new code.
2. **Extracting a reusable component** from an activity that already does it well, then wiring it here.
   Motion that lives inside one activity's manager can only be copied, and copies drift.
3. **New code in the activity**, only for motion nothing else needs.

Flag hand-written motion that duplicates a shared component. List every prefab and shared script a fix
touches, and who else uses it: polish edits spread. Keep fixes out of scene files; put them in prefabs or
data.

Stop here and show the plan. Nothing changes until the person approves it.

## 5. Apply and verify

One beat at a time. For each fix:

- **Test the exit paths.** Every animation must leave the object at rest however it ends: finished,
  interrupted, disabled, rebuilt, or superseded by another animation. An EditMode test that drives the
  interrupt path is worth more than one for the happy path.
- **Watch it.** Capture the beat before and after, or record a short clip (`references/recording.md`).
  Motion can't be judged from a still.
- **Check the neighbours.** A changed hover or fade is usually shared; open one other activity that uses it.

Report per beat: what changed, the evidence, and anything left for a later pass.
