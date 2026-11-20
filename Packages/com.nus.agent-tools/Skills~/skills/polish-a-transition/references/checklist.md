# Checklist, beat by beat

A beat passes when every line that applies holds. The defaults in brackets are only for a project with no motion
vocabulary of its own; a project's own values always win.

## Enter

- The panel arrives with a short fade and a small settle, not an instant SetActive. [0.2–0.3 s, from ~98% scale]
- Only alpha and scale animate, so a layout group that owns the panel's position keeps it.
- It runs in unscaled time: a panel opened while the game is paused still animates.
- Input waits until the panel is readable, or the first click lands on a half-faded control.

## Reveal

- Content that arrives as a set (a hand of cards, a column of options, a diagram's nodes) arrives in a readable
  order with a short stagger, not all on one frame. [~0.05–0.1 s apart, each ~0.3–0.45 s]
- The reveal waits for whatever introduces the activity (an intro line, a briefing) to close. Dealt behind a
  dialogue, it is wasted.
- Items are not draggable mid-flight; they unlock as they land.
- A landing reads as a landing: a small overshoot or settle, not a dead stop. [~1.05–1.08×]
- A Reset re-plays the reveal, so a restart feels like a fresh deal, not a teleport.

## Hover

- Everything the player can use responds on hover; nothing they can't use does.
- Every item of the same kind uses the same hover treatment and values. [lift ~1.03×]
- The hover is driven by the shared feedback component, not hand-written scaling in `Update`.
- After an item moves (dealt, dropped, re-laid out), its hover resting position is re-captured, or the next
  hover lifts from where it used to be.

## Pick

- A press dips, so the player feels the grab. [~0.95×]
- A grabbed item draws above its neighbours (sibling order or an overlay), and comes back to its own place.

## Drag

- The item follows the pointer without lag, and raycasts pass through it to the drop targets.
- Valid targets show they would accept it; invalid ones do not light up.
- Nothing else on screen moves on its own while the player drags.

## Drop

- An accepted drop eases into its slot, not a jump. [~0.2–0.35 s]
- A refused drop, or a drop on nothing, eases back to where it came from, so the player sees the refusal.
- A drop that changes a layout (a fan, a list) re-lays the others smoothly, not on one frame.

## Submit

- Submit looks disabled until the activity can be submitted, and is not just disabled.
- A confirmation, if any, is the shared one, worded the same as everywhere else.
- After a correct submit, Submit and Reset go away so a graded answer cannot be changed.

## Verdict

- Right and wrong use the house colours and the same treatment in every activity.
- The verdict lands on the item that earned it, not only in a banner.
- A wrong answer explains where, then lets the player try again without a full reset.
- Verdict colours clear when the player edits that item again, not before.

## Attention

- When the game points at something, the cue is on the thing itself (a pulse, an outline), and the view
  brings it into sight.
- The view follows the cue, not the logic: if one bar flashes, the camera frames that bar, not whatever the
  code considers "affected".
- The cue survives a rebuild of the thing it marks.
- The cue ends when its job is done, and the item returns to its resting look on every way out.
- While the player is reading a result, the view holds still.

## Debrief

- The way on appears only after the debrief ends, in the place the player is already looking.
- Controls that could change the graded answer are hidden while it plays.
- The way on is one click and cannot fire twice.

## Exit

- The activity fades out or hands over cleanly; the next screen does not pop in over a half-faded one.
- Nothing from the activity (a stray Continue, a flash, a held view) leaks into the next step.

## Engineering checks (every beat)

- **One owner per animated property.** Two systems writing the same position or colour fight, and the result
  depends on script order.
- **Every exit path restores rest**: finished, interrupted, disabled, destroyed and rebuilt, superseded by
  another animation. A coroutine stopped from outside never reaches its own cleanup line.
- **Unscaled time** for anything that can run while the game is paused.
- **No per-frame allocations** in the animation loop (no new lists, LINQ, string building, or scene searches).
- **A player action owns its own visual.** While a drag or press drives an item's look, an ambient animation
  on the same item waits.
- **State is re-found, not cached across rebuilds.** A reference to a UI object that a rebuild destroys is
  null afterwards; re-attach by identity (the data it shows), throttled, not by object.
