# Unity toolkit skills for Claude Code

Skills for any Unity project. They ship with the `com.nus.agent-tools` package so the C# they call is always the
matching version. Unity ignores this folder (its name ends in `~`).

| Skill | What it does | Needs |
|---|---|---|
| `unity-scene-safe-edit` | Changes a scene or prefab so the diff holds only what you meant; splices one change out of a churned save, removes a single override | Python 3, git |
| `unity-wiring-diagnose` | Reads prefab and scene YAML to show how a component is really wired, before you change code | Python 3 |
| `unity-compile-check` | Compiles any assembly with the editor's own Roslyn while the editor holds the project lock | Python 3, a Unity Hub editor install |
| `run-unity-tests` | Runs EditMode tests in a shared editor without blocking it; reports only new failures | the `com.nus.agent-tools` package, Unity MCP |
| `json-binding-audit` | Finds authored JSON keys no C# field reads | Python 3 |
| `keep-content-out-of-scenes` | Designs features so copy and per-step content live in data, and audits a scene for content that should move | Python 3 |
| `ticket-proof` | Proof of work on an Azure DevOps ticket: reads it, captures the Game view or takes your files (stills and clips, flat or VR), outlines, captions, previews, posts and sets Done on request | Python 3, the Azure CLI, `.claude/ticket-board.json` |

The folder is a Claude Code plugin (`.claude-plugin/plugin.json` plus `skills/`). Skills appear as
`/nus-unity-toolkit:<skill>`; Claude also picks them up on its own from their descriptions.

Install steps are in the repository's README.
