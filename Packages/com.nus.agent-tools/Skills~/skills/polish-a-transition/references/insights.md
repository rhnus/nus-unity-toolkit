# Insights

Rules learned from real polish passes. Each one cost a debugging session to find. When a pass teaches a new
one, add it here in the same shape: the rule, why, and how to check.

## Attention and the camera

1. **The camera follows the cue, not the logic.** If the screen flashes one item and the view frames another
   ("the first affected item"), the player sees a flash they can't find. Move the view only when the cue
   moves. *Check:* at every moment a cue is on screen, is its item inside the viewport?

2. **Hold the view while the player reads.** A result screen over a chart invites a rebuild of the chart
   behind it (new data, a re-fit, a restored scroll), and each can scroll the view. Pin the scroll position
   for as long as the result is up, and release it when the player moves on. *Check:* force the view
   elsewhere while the result is up; it should snap back.

3. **A cue must survive a rebuild.** Applying a choice often destroys and recreates the items on screen, and a
   pulse attached to the old object dies silently. Remember what the cue marks by identity (the data row, not
   the GameObject) and re-attach when the object is gone. Throttle the re-find; scene searches allocate.

4. **Hand over between cues; never leave a gap.** If one cue ends on Confirm and the next starts only when the
   player presses on, the screen between shows nothing. The first cue keeps running until the next takes over.

## Exit paths

5. **A colour flash restores its resting colour on every way out.** Stopping a coroutine from outside skips
   its last line. Every stop method resets the colour itself, and a "clear" call made for one kind of flash
   must not kill another kind it doesn't own.

6. **A held state needs a release on every path that closes it.** A view hold, an input lock or a hidden
   control must be undone wherever the screen can close (each button, a disable, a scene change), or the
   next screen inherits it. Put the release in the shared teardown, not in one button's handler.

7. **A control revealed for one step can leak into the next.** A "Continue" built for a debrief and left
   visible becomes a way to skip the next board. When an activity (re)starts, put away anything only its
   previous ending should show.

## Reveal and landing

8. **Deal after the intro, not behind it.** A reveal that plays while an introduction covers the board is
   wasted. Hold the content in its start pose until the intro closes, then play it.

9. **A short stagger reads as a deal; a long one reads as lag.** Under about 0.1 s apart, the set reads as
   one gesture. Keep the total under about a second, whatever the item count.

10. **Lock input in flight, unlock on landing.** A card grabbed mid-flight fights the flight for its position.

11. **Re-capture the rest pose after any move.** Hover feedback that remembers where an item used to be lifts
    it from the wrong place after a deal, a drop or a re-layout.

## Feel

12. **Hover and press values are a pair across the whole game.** One activity at 1.05× and another at 1.02×
    make both feel off. Change the shared value, never one activity's copy.

13. **Disabled must look disabled.** A dead button in its live colour is worse than no button: players click
    it and decide the game is broken.

14. **Pausing the game must not freeze the interface.** UI motion uses unscaled time; only the world uses
    scaled time.

15. **An override that skips the base loses the shared feel.** A drag item that overrides the begin and end of a
    drag without calling the base silently drops the shared pickup sound, the eased return home and the hover
    suppression. *Check:* every override of a shared drag or feedback method calls the base, or the audit says
    which parts it replaces and why.

16. **Rate the time-base risk by what the game does.** "Uses scaled time" only breaks if something sets the time
    scale to 0. Search for writes to it before calling it broken: if nothing pauses that way, it is a latent
    risk worth a cheap fix, not a live bug.

17. **Grade colours clear on one rule across activities.** If one activity clears a wrong mark when the player
    edits the item and another keeps it until the next submit, players learn two meanings for the same red.

## Anti-patterns

- Hover scaling hand-written in `Update` instead of the shared feedback component.
- A tween with no owner of the final value (the next layout pass snaps it, or it ends a pixel off).
- `Find`, `GetComponent` or a scene search inside an animation loop.
- An instant `SetActive(true)` on a panel the player watches appear.
- Two systems animating one property (a layout group and a tween on the same position).
- A per-activity copy of a motion another activity already does well.
