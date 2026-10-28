"""Publish this package to its GitHub repository: pull merged pull requests, push fixes, release a version.

Works in two places, chosen by whether the git repository you run it in IS the package's GitHub repository:

  * a clone of the GitHub repository (standalone): plain git pull / push, tags made locally;
  * a host project that embeds the package as a folder (embedded, e.g. ADGBL): the folder's history is copied out
    with git subtree. Each publish records where it got to, so the next one walks only the commits since then.

    python Tools~/publish.py status            # what GitHub has that this copy doesn't, and the reverse
    python Tools~/publish.py pull              # bring GitHub's main into this copy
    python Tools~/publish.py push              # publish this copy's committed changes to GitHub's main
    python Tools~/publish.py release 0.3.1     # bump, date the CHANGELOG, commit, publish, tag v0.3.1

Run it from anywhere inside the repository. Uncommitted work elsewhere in the repository is never touched or
committed: commits name the package's files explicitly, and nothing here needs a clean working tree.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = "main"


def repository_url():
    """package.json's "repository" field: the one place to change when the repository moves (MIGRATION.md)."""
    with open(os.path.join(PACKAGE_DIR, "package.json"), encoding="utf-8") as handle:
        repository = json.load(handle).get("repository")
    url = repository.get("url") if isinstance(repository, dict) else repository
    if not url:
        sys.exit('package.json has no "repository": { "url": "..." } to publish to.')
    return re.sub(r"^git\+", "", url)


# PUBLISH_REMOTE overrides it, for testing against a scratch repository.
REMOTE = os.environ.get("PUBLISH_REMOTE") or repository_url()
VERSION_FILES = ["package.json", "Skills~/.claude-plugin/plugin.json"]
CHANGELOG = "CHANGELOG.md"


def git(*args, check=True, capture=True, cwd=None):
    result = subprocess.run(["git", *args], cwd=cwd or PACKAGE_DIR, text=True,
                            capture_output=capture, encoding="utf-8")
    if check and result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{(result.stderr or result.stdout or '').strip()}")
    return (result.stdout or "").strip()


def normalise_url(url):
    return re.sub(r"(\.git)?/?$", "", url.strip().lower().replace("http://", "https://"))


TOP = git("rev-parse", "--show-toplevel")
PREFIX = os.path.relpath(PACKAGE_DIR, TOP).replace("\\", "/")
# A package at the repository root is its own repository; otherwise it is embedded unless a remote is the GitHub one.
EMBEDDED = PREFIX != "." and not any(normalise_url(git("remote", "get-url", r, check=False)) == normalise_url(REMOTE)
                                     for r in git("remote").split())


def fetch_remote():
    git("fetch", "--quiet", REMOTE, BRANCH, cwd=TOP)
    return git("rev-parse", "FETCH_HEAD", cwd=TOP)


def is_ancestor(a, b):
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=TOP).returncode == 0


def package_dirty():
    return git("status", "--porcelain", "--", ".")


# ---- Embedded: the package is a folder of a bigger repository ----

def split():
    """The package folder's history as commits whose root is the package. Fast after the first run: it stops at the
    last publish, which push records as a join commit in the host repository."""
    print("Copying the package's history out (the first run in a repository walks all of it)...")
    return git("subtree", "split", f"--prefix={PREFIX}", cwd=TOP).splitlines()[-1]


def record_join(subject, tree, split_sha):
    """A host commit whose second parent is the published history, in the format `git subtree split` reads: the
    mainline commit maps to `split_sha`, so the next split starts from there instead of walking all history.
    Built with commit-tree and update-ref, so it needs neither a clean working tree nor an untouched index."""
    head = git("rev-parse", "HEAD", cwd=TOP)
    message = (f"{subject}\n\ngit-subtree-dir: {PREFIX}\ngit-subtree-mainline: {head}\n"
               f"git-subtree-split: {split_sha}")
    commit = git("commit-tree", tree, "-p", head, "-p", split_sha, "-m", message, cwd=TOP)
    git("update-ref", "-m", f"publish: {subject}", "HEAD", commit, head, cwd=TOP)


def host_tree_with_package(package_tree):
    """HEAD's tree with the package folder replaced by `package_tree`, built in a scratch index."""
    index = os.path.join(git("rev-parse", "--absolute-git-dir", cwd=TOP), "publish-index")
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        for args in (["read-tree", "HEAD"], ["rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", PREFIX],
                     ["read-tree", f"--prefix={PREFIX}/", package_tree]):
            subprocess.run(["git", *args], cwd=TOP, env=env, check=True, capture_output=True)
        return subprocess.run(["git", "write-tree"], cwd=TOP, env=env, check=True, capture_output=True,
                              text=True).stdout.strip()
    finally:
        if os.path.exists(index):
            os.remove(index)


def embedded_pull():
    """Merges GitHub's main into the package folder without git merge, which refuses to run while anything is
    staged anywhere in the host repository. Only the package folder's files change on disk."""
    remote = fetch_remote()
    if package_dirty():
        sys.exit("The package has uncommitted changes. Commit or stash them, then pull.")
    ours = split()
    if is_ancestor(remote, ours):
        print("Already up to date with GitHub.")
        return

    if is_ancestor(ours, remote):
        merged, package_tree = remote, git("rev-parse", f"{remote}^{{tree}}", cwd=TOP)
    else:
        result = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", ours, remote], cwd=TOP,
                                text=True, capture_output=True, encoding="utf-8")
        lines = result.stdout.strip().splitlines()
        if result.returncode != 0:
            # Output: the tree, the conflicted paths, a blank line, then messages.
            conflicted = lines[1:lines.index("")] if "" in lines else lines[1:]
            sys.exit("GitHub and this copy changed the same lines in:\n  " + "\n  ".join(conflicted) +
                     "\nNothing was changed. Make those files match GitHub's version (or move your edit into a "
                     "pull request there), commit, and pull again.")
        package_tree = lines[0]
        merged = git("commit-tree", package_tree, "-p", ours, "-p", remote, "-m",
                     f"Merge GitHub {BRANCH} with the host's changes", cwd=TOP)

    record_join(f"Merge GitHub {BRANCH} into '{PREFIX}/'", host_tree_with_package(package_tree), merged)
    git("restore", "--source=HEAD", "--staged", "--worktree", "--", PREFIX, cwd=TOP)
    print(f"Pulled GitHub's {BRANCH} into {PREFIX}." + ("" if merged == remote else " Run push to publish the merge."))


def embedded_push():
    if package_dirty():
        print("Note: the package has uncommitted changes; only committed work is published.")
    sha = split()
    remote = fetch_remote()
    if not is_ancestor(remote, sha):
        sys.exit(f"GitHub's {BRANCH} has commits this copy doesn't. Run `publish.py pull` first, then push again.")
    head_tree = git("rev-parse", "HEAD^{tree}", cwd=TOP)
    if remote == sha:
        if not is_ancestor(sha, "HEAD"):   # a publish made without this script: record it so later runs start here
            record_join(f"Record publish of '{PREFIX}/' as {sha[:9]}", head_tree, sha)
        print("GitHub already has everything; nothing to publish.")
        return sha
    git("push", REMOTE, f"{sha}:refs/heads/{BRANCH}", cwd=TOP)
    # A split commit may be recorded once only (git subtree refuses a second record); a pull's merge already is.
    if not is_ancestor(sha, "HEAD"):
        record_join(f"Publish '{PREFIX}/' as {sha[:9]}", head_tree, sha)
    print(f"Published {sha[:9]} to {REMOTE} {BRANCH}.")
    return sha


# ---- Standalone: a clone of the package's own repository ----

def standalone_pull():
    git("pull", "--ff-only", REMOTE, BRANCH, cwd=TOP, capture=False)


def standalone_push():
    git("push", REMOTE, f"HEAD:refs/heads/{BRANCH}", cwd=TOP, capture=False)
    return git("rev-parse", "HEAD", cwd=TOP)


# ---- Commands ----

def status():
    remote = fetch_remote()
    print(f"mode     {'embedded in ' + TOP if EMBEDDED else 'standalone clone'}")
    print(f"package  {PREFIX}")
    head = split() if EMBEDDED else git("rev-parse", "HEAD", cwd=TOP)
    if head == remote:
        print("in sync with GitHub")
    elif is_ancestor(remote, head):
        print("ahead of GitHub: `push` publishes it")
    elif is_ancestor(head, remote):
        print("behind GitHub: `pull` brings it in")
    else:
        print("both changed: `pull`, resolve any conflict, then `push`")
    if package_dirty():
        print("uncommitted changes in the package (not published until committed)")


def bump(version):
    paths = []
    for rel in VERSION_FILES:
        path = os.path.join(PACKAGE_DIR, rel)
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
        new, count = re.subn(r'("version"\s*:\s*")[^"]+(")', rf"\g<1>{version}\g<2>", text, count=1)
        if count != 1:
            sys.exit(f"no version field in {rel}")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(new)
        paths.append(rel)

    path = os.path.join(PACKAGE_DIR, CHANGELOG)
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    unreleased = re.compile(r"^## Unreleased[ \t]*(?=\r?$)", re.M)
    if not unreleased.search(text):
        sys.exit("CHANGELOG.md has no '## Unreleased' section. Describe the change there first, then release.")
    text = unreleased.sub(f"## {version} — {datetime.date.today().isoformat()}", text, count=1)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return paths + [CHANGELOG]


def release(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit("version must look like 1.2.3")
    tag = f"v{version}"
    if git("ls-remote", "--tags", REMOTE, f"refs/tags/{tag}", cwd=TOP):
        sys.exit(f"{tag} already exists on GitHub.")
    if EMBEDDED:
        embedded_pull()
    else:
        standalone_pull()

    files = bump(version)
    git("add", "--", *files)
    git("commit", "-m", f"release: {tag}", "--", *files, capture=False)

    sha = embedded_push() if EMBEDDED else standalone_push()
    if EMBEDDED:
        git("push", REMOTE, f"{sha}:refs/tags/{tag}", cwd=TOP)
    else:
        git("tag", "-a", tag, "-m", tag, cwd=TOP)
        git("push", REMOTE, tag, cwd=TOP)
    print(f"Released {tag}. Projects move to it by changing #<tag> in their manifest and `claude plugin update`.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("pull")
    sub.add_parser("push")
    rel = sub.add_parser("release")
    rel.add_argument("version")
    args = parser.parse_args()

    if args.command == "status":
        status()
    elif args.command == "pull":
        embedded_pull() if EMBEDDED else standalone_pull()
    elif args.command == "push":
        embedded_push() if EMBEDDED else standalone_push()
    else:
        release(args.version)


if __name__ == "__main__":
    main()
