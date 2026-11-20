# Changelog

## Unreleased

- **`polish-a-transition` skill**: audits a UGUI activity's motion beat by beat (enter, reveal, hover, pick, drag,
  drop, submit, verdict, attention, debrief, exit) against the project's motion vocabulary, writes a gap table,
  and applies only an approved plan. Ships a per-beat checklist, a list of insights from real polish passes, and a
  starter vocabulary for projects without one.
  - `scripts/motion_scan.py` finds the common motion smells in an activity's scripts in under a second (scaled
    time, per-frame yields, searches and allocations in `Update`, input overrides that skip their base, hard-coded
    colours, direct scale writes, panels popped in with `SetActive(true)`), each as a lead to confirm.
  - The audit checks every claim before calling it Broken, and adds **Latent** and **Unconfirmed** verdicts.
  - `references/survey-brief.md` is the brief for a subagent surveying a large activity;
    `references/recording.md` covers recording a beat with Unity's Recorder from `Unity_RunCommand`.

## 0.5.0 — 2026-10-30

- **`Skills~/scripts/export_agents.py`**: copies the skills into a project for coding agents other than Claude Code.
  Writes `.github/skills/<skill>/` (GitHub Copilot) and a marked section in `AGENTS.md` (Codex, Cursor, Gemini CLI);
  `--targets agents` writes `.agents/skills/`. `${CLAUDE_SKILL_DIR}` becomes the copy's path from the repository
  root, skills that call the Unity editor are marked as needing the Unity MCP bridge, and the skills' own tests and
  caches are left out. `--check` exits 1 when the copies are out of date; `--off` removes only what it wrote (the two can't be combined). A
  project's own skill of the same name is never overwritten. It ships in the Unity package, so it runs without
  Claude Code.

## 0.4.0 — 2026-10-29

- **`ticket_proof.py pr <number> --session <folder>`**: posts a session folder written by the Unity dev tools
  (`proof.json`, `report.md`, `report-pr.md`, screenshots, recordings) to a pull request. It only previews unless
  `--confirm` is given; the preview prints the target, the files with sizes and the exact comment. `--confirm`
  uploads every file as a pull request attachment, rewrites the report's file links to the attachment URLs (PNGs
  inline), posts one comment thread, reads it back and records the thread and URLs in `<session>/proof-posted.json`.
  A session already posted needs `--again`. `--also-ticket N` then posts the same files to that ticket. Existing
  commands are unchanged.

## 0.3.0 — 2026-10-29

- **`ticket-proof` takes pull requests**: `--pr N` in place of `--ticket N` on `lookup`, `attach`, `status`,
  `remove` and `post`. `lookup --pr` gives the pull request's branches, head commit, reviewers, description, linked
  tickets and comments. `post --pr` uploads the files as the pull request's attachments and posts one Markdown
  comment thread, closed so it never holds up a comment-resolution policy, and warns when the capture's commit is
  not the pull request's head. Captures wait in `pr-N/`. Ticket behaviour is unchanged.

## 0.2.0 — 2026-10-28

- **`ticket-proof` skill**: proof of work on Azure DevOps tickets for flat and VR games. Its script reads the
  board from `.claude/ticket-board.json` (or the git remote), queues stills and clips with outlines and captions,
  previews the comment, and posts it with an optional move to Done. Scratch tickets (990000+) never post.
- **`Tools~/publish.py`**: `status`, `pull`, `push` and `release <version>` (pull, bump both versions, date the
  CHANGELOG, commit, push, tag). **CONTRIBUTING.md** says how to send a change and ship an urgent fix.
- **Ready to move accounts:** the repository's address is `package.json`'s `repository` field, which `publish.py`
  reads. **MIGRATION.md** is the step-by-step move to another GitHub account without breaking any project.

## 0.1.0

First release, moved out of ADGBL's `Assets/Editor/AgentTools` and `.claude/skills`.

- `NUS.AgentTools.AgentTestRunner` (namespaced; ADGBL's copy was global). Known failures are read from the
  project's `.claude/known-test-failures.txt`.
- Skills, as the `nus-unity-toolkit` Claude Code plugin: `unity-scene-safe-edit`, `unity-wiring-diagnose`,
  `unity-compile-check` (now takes any asmdef name), `run-unity-tests`, `json-binding-audit`,
  `keep-content-out-of-scenes`. Scripts are referenced through `${CLAUDE_SKILL_DIR}`.
