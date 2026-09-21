#!/usr/bin/env python3
"""Report which local files still need uploading to github.com.

There is no local git, so nothing tracks what has been dragged over and what
has not. This asks the repository what it holds, hashes the local files the
same way git would, and lists the difference.

Read-only, no credentials: the repository is public.

    python3 scripts/pending.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "tagawa/ClassicMotoringJapan"
BRANCH = "main"
ROOT = Path(__file__).resolve().parent.parent

# Mirrors .gitignore. Matched by name at any depth, which is what those
# patterns mean to git too, since none of them is anchored with a slash.
SKIP_DIRS = {"site", ".venv", "__pycache__", ".git"}
SKIP_ANYWHERE = {".DS_Store"}
# Withheld from the public repo on purpose: the spec and the operating notes
# stay private (see CLAUDE.md). Only the copies at the top level.
SKIP_ROOT_DIRS = {"docs"}
SKIP_ROOT_FILES = {"README.md", "CLAUDE.md"}


def blob_sha(data: bytes) -> str:
    """The object name git would give this content, so hashes can be compared."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def local_manifest(root: Path) -> dict[str, str]:
    """Every file that belongs in the repository, by path, with its git hash."""
    found = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if set(parts[:-1]) & SKIP_DIRS or parts[-1] in SKIP_ANYWHERE:
            continue
        if parts[0] in SKIP_ROOT_DIRS or (len(parts) == 1 and parts[0] in SKIP_ROOT_FILES):
            continue
        found[rel.as_posix()] = blob_sha(path.read_bytes())
    return found


def compare(local: dict[str, str], remote: dict[str, str]):
    """Return (new, changed, remote_only) as sorted path lists."""
    return (
        sorted(p for p in local if p not in remote),
        sorted(p for p in local if p in remote and local[p] != remote[p]),
        sorted(p for p in remote if p not in local),
    )


def fetch_remote(repo: str = REPO, branch: str = BRANCH) -> dict[str, str]:
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        tree = json.load(response)
    # A truncated tree would make files look new that are not, so refuse to guess.
    if tree.get("truncated"):
        raise RuntimeError("GitHub truncated the file listing, so the comparison would be wrong")
    return {x["path"]: x["sha"] for x in tree["tree"] if x["type"] == "blob"}


def main() -> int:
    try:
        remote = fetch_remote()
    except urllib.error.HTTPError as e:
        hint = " (the API allows 60 unauthenticated calls an hour)" if e.code == 403 else ""
        print(f"Could not read {REPO}: HTTP {e.code}{hint}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, RuntimeError, KeyError) as e:
        print(f"Could not read {REPO}: {e}", file=sys.stderr)
        return 1

    local = local_manifest(ROOT)
    new, changed, remote_only = compare(local, remote)

    if new or changed:
        print(f"{len(new) + len(changed)} file(s) to upload to {REPO}:\n")
        for path in new:
            print(f"  new      {path}")
        for path in changed:
            print(f"  changed  {path}")
        print(f"\n{len(local) - len(new) - len(changed)} file(s) already up to date.")
    else:
        print(f"Everything is up to date: all {len(local)} file(s) match {REPO}.")

    if remote_only:
        print(f"\nIn the repo but not here, left alone: {', '.join(remote_only)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
