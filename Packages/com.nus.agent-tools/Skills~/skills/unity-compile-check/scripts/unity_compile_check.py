"""
Compile a Unity script assembly with Roslyn WITHOUT closing the editor.

`Unity.exe -batchmode` cannot open a project the editor already has locked, so the usual headless
compile is unavailable while someone is working. This drives the editor's own Roslyn directly against a
response file rebuilt from the current csproj, which needs no lock at all.

    python unity_compile_check.py                      # Assembly-CSharp
    python unity_compile_check.py --assembly editor    # Assembly-CSharp-Editor
    python unity_compile_check.py --assembly MyGame.UI # any asmdef, by its name
    python unity_compile_check.py --project D:/Path    # explicit project root

Exit code 0 = no real errors. Errors caused by a stale source list are reported separately and do NOT
fail the run -- see classify_errors.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

# Short names for the two assemblies every project has; any other value is taken as an asmdef name.
ALIASES = {
    "runtime": "Assembly-CSharp",
    "editor": "Assembly-CSharp-Editor",
}


def find_project_root(explicit):
    root = os.path.abspath(explicit or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(root, "Assets")) and os.path.isdir(os.path.join(root, "ProjectSettings")):
            return root.replace("\\", "/")
        parent = os.path.dirname(root)
        if parent == root:
            sys.exit("not inside a Unity project (no Assets/ + ProjectSettings/ above the working directory)")
        root = parent


def unity_version(root):
    path = os.path.join(root, "ProjectSettings", "ProjectVersion.txt")
    with open(path, encoding="utf-8") as handle:
        match = re.search(r"m_EditorVersion:\s*(\S+)", handle.read())
    if not match:
        sys.exit("could not read m_EditorVersion from ProjectVersion.txt")
    return match.group(1)


def find_toolchain(version):
    """dotnet.exe + csc.dll from the editor matching the project, falling back to any installed editor."""
    roots = [
        os.path.expandvars(r"%ProgramFiles%/Unity/Hub/Editor"),
        os.path.expandvars(r"%ProgramFiles(x86)%/Unity/Hub/Editor"),
        "/Applications/Unity/Hub/Editor",
    ]
    tried = []
    for base in roots:
        for candidate in ([os.path.join(base, version)] + sorted(glob.glob(os.path.join(base, "*")), reverse=True)):
            data = os.path.join(candidate, "Editor", "Data")
            if not os.path.isdir(data):
                data = os.path.join(candidate, "Unity.app", "Contents")   # macOS layout
            dotnet = glob.glob(os.path.join(data, "NetCoreRuntime", "dotnet*"))
            csc = glob.glob(os.path.join(data, "DotNetSdkRoslyn", "csc.dll")) or \
                  glob.glob(os.path.join(data, "Tools", "Roslyn", "csc.dll"))
            tried.append(candidate)
            if dotnet and csc:
                exact = os.path.basename(candidate) == version
                return dotnet[0], csc[0], os.path.basename(candidate), exact
    sys.exit("no Unity Roslyn toolchain found. Looked under:\n  " + "\n  ".join(tried[:8]))


def build_rsp(root, assembly, outdir):
    """
    Rebuild the response file from live project state.

    Three things make the Bee-generated rsp unusable as-is, and each one produced a confusing failure
    before this script existed:
      * its bare source lines are stale, so a file added since the last Bee build reports CS0246 for a
        type that plainly exists on disk -- sources are taken from the csproj instead;
      * its references point into Library/Bee/artifacts, which the editor may have already replaced --
        those are repointed at Library/ScriptAssemblies;
      * PackageCache paths carry a content hash that changes on resolve -- those are re-globbed by name.
    """
    bee = glob.glob(f"{root}/Library/Bee/artifacts/*.dag/{assembly}.rsp")
    if not bee:
        sys.exit(f"no {assembly}.rsp under Library/Bee/artifacts -- let the editor compile once first")
    base = max(bee, key=os.path.getmtime)

    with open(base, "rb") as handle:
        lines = handle.read().decode("utf-8-sig").splitlines()

    flags, refs = [], []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text.startswith(("-r:", "/r:")):
            refs.append(text)
        elif text.startswith(("-", "/")):
            # Redirect build output into the scratch dir so this never overwrites the editor's own artifacts.
            if text.startswith(("-out:", "-refout:")):
                flag, _, value = text.partition(":")
                name = os.path.basename(value.strip('"').replace("\\", "/"))
                flags.append(f'{flag}:"{outdir}/{name}"')
            else:
                flags.append(text)

    csproj = os.path.join(root, f"{assembly}.csproj")
    if not os.path.isfile(csproj):
        sys.exit(f"{assembly}.csproj not found -- open the project in the editor once to generate it")
    with open(csproj, "rb") as handle:
        listed = re.findall(r'<Compile\s+Include="([^"]+)"', handle.read().decode("utf-8-sig"))
    listed = [s.replace("\\", "/") for s in listed]
    sources = [s for s in listed if os.path.isfile(os.path.join(root, s))]

    fixed = []
    for ref in refs:
        tag, path = ref[:3], ref[3:].strip('"').replace("\\", "/")

        # An assembly must see the dependency built HERE, not the stale one in Library: the editor assembly
        # needs the Assembly-CSharp just compiled, and a test asmdef the asmdef it references. Whichever of the
        # pair ran first left its output in outdir, so prefer that whenever it exists.
        stem = re.sub(r"\.(ref\.)?dll$", "", os.path.basename(path))
        local = next((c for c in (f"{outdir}/{stem}.ref.dll", f"{outdir}/{stem}.dll") if os.path.isfile(c)), None)
        if stem != assembly and local:
            fixed.append(f'{tag}"{local}"')
            continue

        if "Library/Bee/artifacts/" in path:
            name = re.sub(r"\.ref\.dll$", ".dll", os.path.basename(path))
            alt = f"{root}/Library/ScriptAssemblies/{name}"
            if os.path.isfile(alt):
                fixed.append(f'{tag}"{alt}"')
                continue

        absolute = path if os.path.isabs(path) else os.path.join(root, path)
        if not os.path.isfile(absolute):
            match = re.search(r"Library/PackageCache/([^@/]+)@[^/]+/(.*)$", path)
            found = glob.glob(f"{root}/Library/PackageCache/{match.group(1)}@*/{match.group(2)}") if match else []
            if found:
                fixed.append(f'{tag}"{found[0]}"'.replace("\\", "/"))
            continue
        fixed.append(f'{tag}"{path}"')

    rsp = f"{outdir}/{assembly}.rsp"
    with open(rsp, "w", encoding="utf-8") as handle:
        handle.write("\n".join(flags + fixed + [f'"{s}"' for s in sources]) + "\n")
    return rsp, len(sources), len(listed) - len(sources), len(fixed)


def declares_type(root, name):
    """Is `name` declared anywhere under Assets/? Distinguishes a real CS0246 from a stale source list."""
    pattern = re.compile(r"\b(class|struct|enum|interface|record)\s+" + re.escape(name) + r"\b")
    for folder, dirs, files in os.walk(os.path.join(root, "Assets")):
        dirs[:] = [d for d in dirs if d not in (".git", "obj", "bin")]
        for filename in files:
            if not filename.endswith(".cs"):
                continue
            path = os.path.join(folder, filename)
            try:
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    if pattern.search(handle.read()):
                        return os.path.relpath(path, root).replace("\\", "/")
            except OSError:
                continue
    return None


def unlisted_sources(root):
    """
    .cs files under Assets/ that no csproj lists. Unity writes the csproj only when it reimports, so a file
    created since then is compiled by NO run of this script -- its own errors go unreported and the run still
    says PASS. Only files newer than the newest csproj count; older unlisted ones are excluded on purpose
    (e.g. Editor code of a disabled platform).
    """
    projects = glob.glob(os.path.join(root, "*.csproj"))
    if not projects:
        return []
    listed = set()
    for project in projects:
        with open(project, "rb") as handle:
            for include in re.findall(r'<Compile\s+Include="([^"]+)"', handle.read().decode("utf-8-sig")):
                listed.add(os.path.normcase(os.path.normpath(os.path.join(root, include))))
    newest = max(os.path.getmtime(p) for p in projects)

    missing = []
    for folder, dirs, files in os.walk(os.path.join(root, "Assets")):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not d.endswith("~")]
        for filename in files:
            if not filename.endswith(".cs"):
                continue
            path = os.path.join(folder, filename)
            if os.path.normcase(os.path.normpath(path)) not in listed and os.path.getmtime(path) > newest:
                missing.append(os.path.relpath(path, root).replace("\\", "/"))
    return sorted(missing)


def classify_errors(root, errors):
    """
    Split errors into real breaks and artefacts of a stale source list.

    A CS0246 naming a type that IS declared under Assets/ means the response file predates that file --
    the code is fine and the rsp needs regenerating. Reporting those as breaks sends you hunting a bug
    that does not exist, which has happened more than once.
    """
    real, stale = [], []
    for line in errors:
        match = re.search(r"error CS0246: The type or namespace name '([^']+)'", line)
        if match:
            found = declares_type(root, match.group(1))
            if found:
                stale.append((line, match.group(1), found))
                continue
        real.append(line)
    return real, stale


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assembly", default="runtime",
                        help="runtime, editor, or the name of any asmdef (default: runtime)")
    parser.add_argument("--project", default=None)
    parser.add_argument("--out", default=None, help="scratch dir for the rsp and build output")
    parser.add_argument("--show-warnings", action="store_true")
    args = parser.parse_args()

    root = find_project_root(args.project)
    assembly = ALIASES.get(args.assembly, args.assembly)
    version = unity_version(root)
    dotnet, csc, used, exact = find_toolchain(version)

    outdir = args.out or os.path.join(tempfile.gettempdir(), "claude-unity-compile", os.path.basename(root))
    os.makedirs(outdir, exist_ok=True)
    outdir = outdir.replace("\\", "/")

    print(f"project  {root}")
    print(f"unity    {version}" + ("" if exact else f"  (WARNING: using {used}, no exact match installed)"))
    print(f"assembly {assembly}")

    # The rsp carries project-relative source paths, so csc MUST run with the project root as cwd.
    # Running it from anywhere else yields hundreds of CS2001 "source file could not be found".
    rsp, n_src, n_missing, n_refs = build_rsp(root, assembly, outdir)
    print(f"sources  {n_src} compiled" + (f", {n_missing} listed but absent" if n_missing else ""))
    print(f"refs     {n_refs}")

    result = subprocess.run([dotnet, csc, f"@{rsp}"], cwd=root, capture_output=True, text=True)
    output = (result.stdout or "") + (result.returncode and result.stderr or "")

    errors = [l for l in output.splitlines() if "error CS" in l]
    warnings = [l for l in output.splitlines() if "warning CS" in l]
    real, stale = classify_errors(root, errors)

    print()
    unlisted = unlisted_sources(root)
    if unlisted:
        print(f"-- {len(unlisted)} new .cs file(s) NOT COMPILED by this check (no csproj lists them yet) --")
        for path in unlisted[:10]:
            print(f"   {path}")
        print("   Their errors are invisible here. Have the editor reimport (focus Unity, or AssetDatabase.Refresh")
        print("   via Unity_RunCommand) and re-run, or check them with the run-unity-tests skill's Compile step.")
        print()

    if stale:
        print(f"-- {len(stale)} error(s) from a STALE SOURCE LIST, not from your code --")
        for _, name, where in stale[:10]:
            print(f"   {name} is declared in {where} but was absent from the rsp")
        print("   (harmless here; the list is rebuilt from the csproj on every run)")
        print()

    if real:
        print(f"FAIL - {len(real)} error(s):")
        for line in real[:40]:
            print("  " + line.strip())
    else:
        print(f"PASS - 0 errors, {len(warnings)} warning(s)")

    if args.show_warnings:
        for line in warnings[:60]:
            print("  " + line.strip())

    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
