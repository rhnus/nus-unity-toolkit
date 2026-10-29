# Changelog

## Unreleased

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
