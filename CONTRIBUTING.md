# Contributing to the NUS Unity toolkit

## Never edit an installed copy

In a project, the package sits in `Library/PackageCache` and the skills in Claude Code's plugin cache. Both are
overwritten on the next update. Change this repository instead.

## Send a change

1. **Branch or fork** <https://github.com/rhnus/nus-unity-toolkit>.
2. **Try it in your project** before opening a pull request:
   - the package: in `Packages/manifest.json`, point at your clone (don't commit this line):
     `"com.nus.agent-tools": "file:C:/path/to/clone/Packages/com.nus.agent-tools"`
   - the skills: `claude plugin marketplace add C:/path/to/clone`, then install the plugin from that marketplace.
3. **Describe the change** under `## Unreleased` at the top of `Packages/com.nus.agent-tools/CHANGELOG.md`.
4. **Open a pull request** to `main`, one change per pull request.

Rules for a skill (the README's **What else to share** has why):

- Nothing specific to one project: no paths, scene names, ticket numbers or people. A project's specifics go in its
  own CLAUDE.md.
- Scripts live in the skill's own `scripts/` folder and are referenced as `${CLAUDE_SKILL_DIR}/scripts/…`.
- C# a skill calls goes in the package (`Editor/`), with a `.meta` for every file, because a package installed from
  git is read-only. Unity_RunCommand can't reference package code, so a skill calls it by name.

## Urgent fix (maintainers)

```
# fix it, describe it under "## Unreleased" in the package CHANGELOG, commit
python Packages/com.nus.agent-tools/Tools~/publish.py release 0.1.1
```

`release` pulls first, bumps `package.json` and the plugin's version, dates the CHANGELOG entry, commits only those
files, pushes and tags `v0.1.1`. Then each project moves to it:

- **The package:** change `#v0.1.0` to `#v0.1.1` in `Packages/manifest.json`.
- **The skills:** update the plugin (`/plugin` in Claude Code, or `claude plugin update nus-unity-toolkit@nus-unity-toolkit`).

**A fix to a skill's wording only** doesn't need a release: commit it and run `publish.py push`. Projects get it at
their next plugin update. A skill change that needs new package code waits for the release that ships it.

`python Packages/com.nus.agent-tools/Tools~/publish.py status` says whether your clone is ahead of or behind GitHub.

## Versions

`MAJOR.MINOR.PATCH`. **Patch** for fixes. **Minor** for a new skill or tool that existing projects can ignore.
**Major** when a project has to change something to upgrade, with the steps in the CHANGELOG entry.
