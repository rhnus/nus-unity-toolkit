# NUS Unity toolkit

Reusable tools for Unity projects worked on with Claude Code. One repository, two things to install:

| Part | What it is | Where |
|---|---|---|
| **Agent Tools** | A Unity package: editor tools agents drive through the Unity MCP server, such as `AgentTestRunner` | `Packages/com.nus.agent-tools/` |
| **Skills** | The Claude Code plugin `nus-unity-toolkit`: skills for safe scene edits, wiring diagnosis, compile checks, test runs, JSON audits, content out of scenes | `Packages/com.nus.agent-tools/Skills~/` |

They ship together so a skill and the C# it calls are always the same version. The repository root is also a
Claude Code marketplace (`.claude-plugin/marketplace.json`).

## Install in a project

Use the release tag you want in place of `v0.1.0`.

**1. The Unity package.** Package Manager ▸ + ▸ **Add package from git URL…**:

```
https://github.com/rhnus/nus-unity-toolkit.git?path=/Packages/com.nus.agent-tools#v0.1.0
```

or add it to `Packages/manifest.json`:

```json
"com.nus.agent-tools": "https://github.com/rhnus/nus-unity-toolkit.git?path=/Packages/com.nus.agent-tools#v0.1.0"
```

**2. The skills**, from the Unity project's folder:

```
claude plugin marketplace add rhnus/nus-unity-toolkit
claude plugin install nus-unity-toolkit@nus-unity-toolkit --scope project
```

`--scope project` records the plugin in the project's `.claude/settings.json`. Commit that file. Each teammate runs
the `install` line once on their machine.

**3. Tell Claude about the project.** The skills are generic; the project's CLAUDE.md says what's specific: which
assemblies exist and where tests go, which scenes are shared, and what the project's known test failures are
(`.claude/known-test-failures.txt`).

Skills from the plugin appear as `/nus-unity-toolkit:<skill>`. A copy of the same skill in the project's
`.claude/skills/` still loads beside it, so remove the old copy when you adopt the plugin and keep one source.

## What else to share

| Kind | Put it |
|---|---|
| Skill or C# tool any Unity project could use | here |
| Skill that only makes sense with one package (e.g. the Design System's) | in that package's own `Skills~/` |
| Skill specific to one project | that project's `.claude/skills/` |
| Personal preference or workflow | `~/.claude/skills/` |

When moving a skill here, strip project specifics (paths, scene names, ticket numbers, people), keep its scripts in
its own folder and reference them as `${CLAUDE_SKILL_DIR}/scripts/…`, and put any C# it calls in the package.

## Releasing and contributing

```
python Packages/com.nus.agent-tools/Tools~/publish.py status            # ahead of or behind GitHub
python Packages/com.nus.agent-tools/Tools~/publish.py release 0.1.1     # pull, bump both versions, date the CHANGELOG, commit, push, tag
```

Describe the change under `## Unreleased` in the package CHANGELOG first; `release` refuses without it. Projects then
change the tag in their manifest and update the plugin. How to send a change, and the urgent-fix route, are in
[CONTRIBUTING.md](CONTRIBUTING.md); moving the repository to another GitHub account
without breaking any project is in [MIGRATION.md](MIGRATION.md).

Every file in the package except under folders ending in `~` needs a `.meta` with a fixed GUID: a package installed
from git is read-only, so Unity can't create them.
