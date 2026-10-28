# Changelog

## Unreleased

- **`Tools~/publish.py`**: `status`, `pull`, `push` and `release <version>` (pull, bump both versions, date the
  CHANGELOG, commit, push, tag). **CONTRIBUTING.md** says how to send a change and ship an urgent fix.

## 0.1.0

First release, moved out of ADGBL's `Assets/Editor/AgentTools` and `.claude/skills`.

- `NUS.AgentTools.AgentTestRunner` (namespaced; ADGBL's copy was global). Known failures are read from the
  project's `.claude/known-test-failures.txt`.
- Skills, as the `nus-unity-toolkit` Claude Code plugin: `unity-scene-safe-edit`, `unity-wiring-diagnose`,
  `unity-compile-check` (now takes any asmdef name), `run-unity-tests`, `json-binding-audit`,
  `keep-content-out-of-scenes`. Scripts are referenced through `${CLAUDE_SKILL_DIR}`.
