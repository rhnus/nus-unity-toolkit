# Survey brief

When an activity is large, hand the code survey to a read-only subagent, one per activity, so their files stay
out of your context. Paste this brief with the blanks filled. It asks for evidence, not verdicts: scoring is
yours, after you check each claim (SKILL.md, step 3).

---

Read-only survey of a Unity UGUI activity's motion and feedback, for a polish audit. Project root: `<path>`.
Do not edit anything.

Activity: **<name>**. Start from `<prefab(s)>` and the scripts they use. When a prefab's script isn't obvious,
match its `m_Script` guid against the `.cs.meta` files. Read the prefabs as well as the scripts: feedback
components, their values and inspector events live there. If the activity runs in parts, map each part and
the hand-over between them.

Scanner leads for these prefabs and their scripts are below. Confirm or dismiss each one in context:

```
<paste motion_scan.py output>
```

For EACH beat, report what the activity does today with `file:line` evidence, and whether it is instant or
animated and how (coroutine, Update lerp, Animator, a feedback component, a CanvasGroup fade):

1. Enter: how the panel or window appears.
2. Reveal: how its content first appears (all at once or staggered).
3. Hover: what usable items do on hover, and which component does it.
4. Pick / drag: what a grabbed item does (scale, sibling order, raycasts).
5. Drop: accepted (snap or ease), refused (snap back or ease back), and any sound.
6. Submit: how the button is gated, and any confirmation.
7. Verdict: how right and wrong are shown (exact colours if hard-coded, motion, sound), and when they clear.
8. Attention: anything that points the player at something.
9. Debrief / continue: what appears after a correct answer, and how.
10. Exit: how the activity is put away.

For any claim that something is broken, give the path that reaches it and anything that might already cover
it (an `OnDestroy` cleanup, a base class doing the work, a flag nothing reads). Mark a claim you could not
trace to the end as **unconfirmed**.

Output: a table (beat | what happens | instant or animated, and how | file:line), then at most 12 gaps, each
with its evidence. Under 700 words.
