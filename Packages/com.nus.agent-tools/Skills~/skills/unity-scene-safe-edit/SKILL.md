---
name: unity-scene-safe-edit
description: Change a Unity scene (.unity) or prefab (.prefab) so the diff holds only what you meant to change, and nothing else is lost or rewritten. Use before editing any scene or prefab, when a git diff of one is far larger than the change, when an edit "disappeared" or reverted, when a scene is open with unsaved changes, before merging a branch that touched the same scene, or when a prefab override has to go. Covers text edits, keeping one change from a Unity save, removing a single override, reloading safely and re-applying after a merge.
---

# Edit a scene or prefab without collateral damage

A `.unity` or `.prefab` is YAML that Unity owns. Two things go wrong, and both look like someone else's bug:

1. **A save rewrites far more than you changed.** Saving from the editor can re-serialize Visual Scripting
   graph JSON, reorder object-reference lists, write newly added script fields, and pick up drift in nested
   prefab overrides. One field change becomes a 4,000-line diff that conflicts with everyone.
2. **An open copy overwrites the file.** If the scene is open in Unity with unsaved changes, Unity does not
   reload it when the file changes on disk. The next save from that copy silently writes the old content
   back over your edit. "My fix disappeared" is almost always this.

The rule: **change the file on disk as text, never save a stale open copy, and check the diff size before
you commit.** The helper does the risky parts:

```bash
S=${CLAUDE_SKILL_DIR}/scripts/scene_yaml.py
python $S check  <file>                      # is the diff only my change, or did a save churn it?
python $S blocks <file> --changed            # which YAML blocks differ from HEAD, with names
python $S splice <file> --ids 123,456        # keep only these blocks from a Unity save, on top of HEAD
python $S remove-mod <file> --target <fileID> --guid <prefab guid> --prop m_AnchorMin.y --value 0
```

Every command keeps the file's line endings (CRLF stays CRLF) and refuses unless its match is exact.
`--dry-run` is available on every command that writes.

## 1. Preflight, before touching anything

- **Who else changed this file?** `git status --short <file>` and `git log -3 -- <file>`. If it already has
  local changes you did not make, stop and ask: another person or agent may be mid-edit. Never
  `git checkout -- <file>` over changes you did not make.
- **Is it open and dirty in Unity?** Ask the editor (through `Unity_RunCommand`):
  ```csharp
  var s = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
  result.Log($"{s.path} dirty={s.isDirty} playing={UnityEditor.EditorApplication.isPlaying}");
  ```
  - **Dirty:** do not edit the file on disk yet. Unity will not reload it, and its next save writes the old
    content back. Ask the person to reopen it and choose **Don't Save**, or to save first if the unsaved
    work is theirs. Do not save or discard it yourself.
  - **In Play mode:** wait. Changes made in Play mode are thrown away, and a test run cannot start.
- **Save a patch of any scene work already in the file** before something risky (a pull, a reload):
  `git diff -- <file> > <scratch>/scene.patch`. That patch is how you get the work back.

## 2. Pick the method by the kind of change

| Change | Method |
|---|---|
| A field value, a UnityEvent call's target or method, a string argument | **Text edit** with the Edit tool. A few lines. |
| A prefab override that should not be there | **`remove-mod`** on the file that stores it (find it with step 4). |
| Structural: a new object, a prefab conversion, an added component | Do it **in Unity and save**, then **`splice`** only its blocks onto HEAD. |
| Content that changes often (copy, which question, which variant) | Move it out of the scene into data, so the scene changes once. |

### Text edits

- Find the block by something unique near it (a step name, a GUID, an `m_Name`), then edit only the lines you
  change. Keep lines with trailing whitespace (`id: `, `customText: `) **out of** your old/new strings: the
  edit can strip the trailing space and produce noise lines.
- For many replacements, script them: read with `newline=""`, require `text.count(old) == 1` for each, and
  write back with `newline=""` so line endings survive.
- Visual Scripting graphs sit in the same file as one long `_json:` string. Never edit inside one by hand.

### Keeping one change out of a churned Unity save

When Unity has to make the change (a prefab conversion, say) and its save rewrote half the file:

1. `python $S blocks <file> --changed`. The blocks your change touched are the ones with your object's
   name, plus any new `PrefabInstance` (class 1001) and `stripped` stand-ins.
2. `python $S splice <file> --ids <those fileIDs> --dry-run`, check the list, then run it without `--dry-run`.
   This rebuilds the file from HEAD and takes only those blocks from the save.
3. `python $S check <file>` should now pass, and the diff should be only those blocks.
4. Reload in Unity (step 3) and check that the object behaves.

A prefab conversion keeps the original component fileIDs as `stripped` blocks, so other objects' references
to them, such as UnityEvent targets, normally need no change. Confirm that after reloading.

## 3. Reload and verify

Only when the scene is **not dirty**:

```csharp
UnityEditor.AssetDatabase.Refresh();
var active = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
if (!active.isDirty) UnityEditor.SceneManagement.EditorSceneManager.OpenScene(active.path);
```

Then read the value back through `SerializedObject` rather than trusting the file. Check that the scene is
still not dirty, and run `check` once more. A prefab on disk is reread with
`AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate)` plus `PrefabUtility.LoadPrefabContents`.

**Do not "fix" a churned diff by saving again.** Saving never shrinks it. Revert the file (only if it was
clean before you started) and re-apply your change as text or with `splice`.

## 4. Overrides: find which layer holds it

A value can be set in the base prefab, overridden in a prefab that nests it, and overridden again by the
scene. A fix in the wrong layer changes nothing, because a higher layer still wins. To find the layer:

- **Each prefab:** `PrefabUtility.LoadPrefabContents(path)` and read the property on each one, from the base
  prefab outwards. The first one showing the wrong value holds the override.
- **The scene:** `PrefabUtility.GetPropertyModifications(PrefabUtility.GetOutermostPrefabInstanceRoot(go))`,
  filtered to the target object. `AssetDatabase.TryGetGUIDAndLocalFileIdentifier(mod.target, ...)` gives
  the `--target` fileID and `--guid` that `remove-mod` needs.
- **Fix every layer that has it.** Check the scene after fixing a prefab: a scene override hides a
  prefab fix completely.

Prefer `remove-mod` to `PrefabUtility.RevertPropertyOverride` plus a save, because that save can rewrite
other nested overrides in the same file.

## 5. Merging with someone else's scene changes

1. Save your scene work as a patch: `git diff -- <file> > <scratch>/mine.patch`.
2. Restore the file: `git checkout -- <file>` (it holds only your work, which is in the patch).
3. Pull or merge. Their version comes in cleanly.
4. `git apply --3way <scratch>/mine.patch`, then `git restore --staged <file>` (`--3way` stages the result).
5. Reload without saving the old open copy (step 3).

If the patch no longer applies, their change touched the same blocks. Take their file and re-make your
change on top, by text edit or in Unity followed by `splice`. Never hand-merge the conflicting YAML.

Keep a short record of each scene change (object, field, before, after, why) next to the work. It lets
anyone re-apply the change after a bad merge without reverse-engineering the diff.

## YAML you will meet

- `--- !u!<classID> &<fileID>` starts each block. Common class IDs: 1 GameObject, 4 Transform,
  224 RectTransform, 114 MonoBehaviour, 1001 PrefabInstance. `stripped` marks a stand-in for an object
  owned by a prefab instance.
- A prefab instance's overrides are `m_Modifications` entries: `target` (fileID and guid in the SOURCE
  prefab), `propertyPath`, `value`, `objectReference`.
- UnityEvent calls: `m_Target`, `m_TargetAssemblyTypeName`, `m_MethodName`, `m_Mode` (1 void, 2 object,
  3 int, 4 float, 5 string, 6 bool) and the matching `m_Arguments` field.
- Enums and masks are stored as ints. `{fileID: 0}` is an empty reference.
- Line endings: with `core.autocrlf`, the working copy is CRLF while git stores LF. The helper handles it;
  hand-written scripts must too.

## Done means

- `python $S check <file>` passes, and the diff contains only the blocks you meant.
- The value reads back correctly in Unity after a reload, with the scene not dirty.
- No unrelated file (font atlases, packages, other scenes) is in the commit.
