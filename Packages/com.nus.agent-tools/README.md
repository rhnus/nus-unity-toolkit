# Agent Tools

Editor tools that AI coding agents drive through the Unity MCP server (`Unity_RunCommand`), plus the Claude Code
skills that use them, in `Skills~/` (see its README).

## AgentTestRunner

`NUS.AgentTools.AgentTestRunner` runs EditMode tests in an editor that the user and other agents share:

- **`Compile(owner)`** reserves the editor for `owner` and imports changed scripts.
- **`Run(patterns, owner, resultsPath)`** runs the tests whose full names match the regex `patterns` (null runs
  everything), releases the editor and returns a summary: `pass=… fail=… (new=…, known=…)`.
- It never waits. It answers `BUSY` when another agent holds the editor (a reservation lapses after 10 minutes),
  and `NOT RUN` in Play mode, while compiling, after a failed compile, or with an unsaved scene, because a test run
  would stop on Unity's save prompt.
- **Known failures** are listed per project in `.claude/known-test-failures.txt`: one full test name per line, `#`
  for comments. A failure on that list reports as `known fail`; any other as `NEW FAIL`.

`Unity_RunCommand` can't reference package code, so agents call it by name. The `run-unity-tests` skill has the
snippet.

## Requirements

Unity 6, and the Test Framework package (`com.unity.test-framework`), which this package depends on.
