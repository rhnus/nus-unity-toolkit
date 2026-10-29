---
name: ticket-proof
description: Prepare and post proof of work (screenshots and short clips) to an Azure DevOps ticket or pull request, for flat and VR Unity games alike. Reads the ticket or pull request (and its linked tickets), works out what each acceptance item needs to show, captures the Game view or takes files the person already has, outlines the change, writes honest captions, previews the comment, and posts it (optionally moving the ticket to Done) only when asked. Use when asked to post proof, screenshots or a recording to a ticket or a pull request, to capture the Game view for a PR comment, to show reviewers what a PR changes, to show a ticket's fix, to close a ticket with evidence, or to list this sprint's tickets.
---

# Proof of work on a ticket or pull request

One script does the board work: `${CLAUDE_SKILL_DIR}/scripts/ticket_proof.py` (call it `TP` below). Run it from the
project folder. Every command prints JSON, or a first line saying what to do.

```bash
TP="${CLAUDE_SKILL_DIR}/scripts/ticket_proof.py"
python "$TP" doctor
```

**Nothing posts without an explicit ask.** Reading, capturing, attaching and previewing are local. `post` changes the
ticket or pull request; add `--done` only when the person asked for Done (tickets only).

**A pull request** takes `--pr N` in place of `--ticket N` in every step below (`lookup`, `attach`, `status`,
`remove`, `post`). The differences are listed under each step.

## 0. Setup (once per project)

`doctor` checks each prerequisite and gives the fix for the first that fails. The board is the project's
`.claude/ticket-board.json` (see the README beside this file), else the Azure DevOps project of the `origin` remote.
Sign-in is the Azure CLI's (`az login`); never ask for a token.

## 1. Read the ticket

`python "$TP" lookup --ticket N` gives the title, state, description, tags and comments (oldest first, `proof: true`
on comments this tool posted). `python "$TP" tickets` lists the current sprint, `"mine": true` on the person's; match
a described ticket against those titles, and ask when two fit.

**A pull request:** `python "$TP" lookup --pr N` gives its title, status, branches, head commit, reviewers,
description, linked `tickets` and people's comments. Take the acceptance items from the linked tickets (`lookup
--ticket` each one) and the description's own checks; with neither, list what the diff changes that a player would
see, and confirm that list with the person before capturing. Capture on the pull request's branch at its head
commit: check `git rev-parse --short HEAD` matches `headCommit`, and that the Unity editor has recompiled.

Number the acceptance items, each with what would prove it. Mark each one **visible** (the player sees it) or
**invisible** (only data, telemetry or an AI changes). An invisible item's proof is text (the tests that cover it,
with results), never a screenshot that shows nothing.

## 2. Choose the capture for each visible item

| The item is about | Capture |
|---|---|
| UI, text, layout, a state shown on screen (most items) | **A still from the Game view** |
| Motion or interaction: grab, teleport, animation, feedback timing | **A clip of 5–15 s** |
| Only visible on a device: passthrough, hand tracking, frame rate, comfort | **A capture on the device** |

Plan 3–5 files per ticket, the fewest that prove every item. Show the same place as any "before" image on the ticket.

## 3. Capture

**A still, in Play Mode**, through `Unity_RunCommand` (the Game view must be open; in VR, set its mirror view to one
eye first, so the shot is not the stereo pair):

```csharp
internal class CommandScript : IRunCommand
{
    public void Execute(ExecutionResult result)
    {
        string path = System.IO.Path.GetFullPath("Artifacts/TicketProof/_incoming/shot.png");
        System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path));
        UnityEngine.ScreenCapture.CaptureScreenshot(path, 1);
        result.Log("capturing to {0}", path);
    }
}
```

The file is written at the end of the frame, so check it exists in the next command, then `Read` it to look at it.
Clear dialogue and pause anything moving first, and check nothing covers the change.

**A clip:** Unity Recorder (the `com.unity.recorder` package), recording the Game view, or any screen recorder.
Keep it short and trimmed to the moment.

**On the device:** the headset's own screenshot or recording, copied off it (for Meta Quest: Meta Quest Developer
Hub, or `adb pull /sdcard/Oculus/Screenshots` and `/sdcard/Oculus/VideoShots`).

**Files the person pasted into the chat** arrive with their saved path; use those.

## 4. Queue, outline, caption

For a pull request, the same command with `--pr N`; files wait in `pr-N/` beside the tickets' folders.

```bash
python "$TP" attach --ticket N --file shot.png clip.mp4 \
    --caption "Item 1 - fixed: <what to look at>." "Item 2 - fixed: <what happens>." \
    --label "Ward 2 · hand-wash station" --outline "x,y,w,h" ""
```

- `--outline` boxes the change (pixels of that image, origin top-left; read its size first); `--crop` keeps one
  region. Images only, and only the queued copy changes. Look at the result before posting: a box on the wrong thing
  is worse than none.
- One caption per file, naming the item and its verdict: `Item 1 - fixed: …` or `Item 2 - not fixed yet: …`.
- `status` lists what is waiting; `remove --file <name>` drops one.

**Claim only what you checked.** "Unchanged", "now bigger", "faster" each need a measurement. A still can't show
motion or sound, so a caption that depends on them says so, or the item gets a clip.

## 5. Preview, then post when asked

```bash
python "$TP" post --ticket N --note "<what it does now, under 15 words>" --preview
```

`--preview` writes the comment as a local page; show its path. `--body <file>` adds a summary between the opening line
and the files (an `.html` fragment, tables welcome); with nothing attached it posts the summary alone, for an item
proven by tests.

When the person asks to post: the same command without `--preview` (plus `--done` if they asked for Done). It uploads
every file to the ticket's Attachments, posts one comment (images inline, clips as links), reads the comment back to
check it, and reports the comment and the state.

**A pull request:** `post --pr N` uploads the files as the pull request's attachments and posts one comment thread in
Markdown (so `--body` is Markdown, a `.md` file), already closed so it never holds up a comment-resolution policy.
It reads the thread back, and returns its link. A `warning` in the result means the capture was made on a different
commit from the pull request's head: recapture, or say so in the report. `--done` is refused.

## 6. Report

The ticket or pull request and its title; per item, fixed / not fixed / proven by tests, with its file; the opening
line and each
caption; anything noticed but not claimed; and the comment link once posted.

## Safety

- Tickets from 990000 up are **scratch**: use them to try a capture; nothing posts from them.
- A ticket that is already finished, or a pull request already completed or abandoned, and already has proof from
  this tool refuses a second post unless `--again`.
- Pull requests have no scratch range: try a pull request's comment with `--preview` or `--dry-run`.
- Files over 60 MB are refused: trim the clip.
