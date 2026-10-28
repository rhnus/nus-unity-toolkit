---
name: run-unity-tests
description: Run Unity EditMode tests in the open, shared editor; reports only NEW failures. Use before reporting Assets/ work as done or when asked to run tests.
---

# Run Unity EditMode tests

The editor is shared with the user and possibly other agents. **Check compiles offline first** with the
`unity-compile-check` skill; it never touches the editor. Use the editor only for tests.

The runner is `NUS.AgentTools.AgentTestRunner` in the `com.nus.agent-tools` package. `Unity_RunCommand` can't
reference package code, so call it by name. Two commands, run separately, with the same short owner name in both;
use a unique one, such as your session id:

```csharp
// 1: reserves the editor; Unity recompiles only if a script changed
internal class CommandScript : IRunCommand
{
    public void Execute(ExecutionResult result)
    {
        var runner = System.Type.GetType("NUS.AgentTools.AgentTestRunner, NUS.AgentTools.Editor");
        result.Log((string)runner.GetMethod("Compile").Invoke(null, new object[] { "sess-4e72" }));
    }
}
```

```csharp
// 2: only the classes you touched; releases the editor when done
internal class CommandScript : IRunCommand
{
    public void Execute(ExecutionResult result)
    {
        var runner = System.Type.GetType("NUS.AgentTools.AgentTestRunner, NUS.AgentTools.Editor");
        result.Log((string)runner.GetMethod("Run").Invoke(null, new object[] { new[] { "^FollowUpEventTests" }, "sess-4e72", null }));
    }
}
```

`GetType` returning null means the package isn't installed, or the editor hasn't compiled it yet.

**Never wait on the editor.** At most two attempts in total per step. Then report "tests not run: editor busy"
together with the offline compile result, and move on.

| Answer | Do |
|---|---|
| `BUSY: reserved by X` | Don't retry. Report it. |
| `COMPILATION_IN_PROGRESS` / `still compiling` | One more try. If it persists, someone else is compiling; report it. |
| `unsaved changes in <scene>` | Ask the user to save. Never save or discard their scene yourself. |
| `play mode` | Ask. Never stop someone's play session. |
| `compile FAILED` | Read the console errors and fix them. |
| `known fail` | Pre-existing (listed in the project's `.claude/known-test-failures.txt`). Only `NEW FAIL` is yours; never list your own regression there. |

**Known failures** live in the project, not in this skill: `.claude/known-test-failures.txt`, one full test name
per line, `#` for comments. Say why each one fails and when it was added, so it can be cleared later.

**Scope:** only the test classes for the code you touched. Run the full suite (pass `null` for the patterns) only
when the user asks to test everything; it freezes the editor for everyone for minutes.
