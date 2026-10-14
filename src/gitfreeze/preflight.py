"""Repo detection, state checks, status parsing, remote probes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import gitcmd
from .errors import PreflightError


@dataclass
class Facts:
    root: Path
    git_dir: Path
    remote: str
    remote_url: str
    branch: str
    head_sha: str


def detect(path, remote: str = "origin", branch: str | None = None) -> Facts:
    path = Path(path).resolve()
    proc = gitcmd.run(path, "rev-parse", "--show-toplevel", check=False)
    if proc.returncode != 0:
        raise PreflightError(f"{path} is not inside a git repository")
    root = Path(os.fsdecode(proc.stdout.strip())).resolve()

    git_dir = Path(os.fsdecode(gitcmd.out(root, "rev-parse", "--absolute-git-dir")))
    url = gitcmd.run(root, "remote", "get-url", remote, check=False)
    if url.returncode != 0:
        raise PreflightError(f"no git remote named '{remote}' here (check: git remote -v)")

    branch_name = branch
    if not branch_name:
        branch_name = os.fsdecode(gitcmd.out(root, "rev-parse", "--abbrev-ref", "HEAD"))
    if not branch_name or branch_name == "HEAD":
        raise PreflightError("detached HEAD — check out a branch first (or pass --branch)")

    head = gitcmd.run(root, "rev-parse", "-q", "--verify", "HEAD", check=False)
    if head.returncode != 0:
        raise PreflightError("this repository has no commits yet")

    _refuse_in_progress(git_dir)
    return Facts(
        root=root,
        git_dir=git_dir,
        remote=remote,
        remote_url=os.fsdecode(url.stdout.strip()),
        branch=branch_name,
        head_sha=os.fsdecode(head.stdout.strip()),
    )


def _refuse_in_progress(git_dir: Path) -> None:
    marks = {
        "MERGE_HEAD": "a merge is in progress",
        "CHERRY_PICK_HEAD": "a cherry-pick is in progress",
        "REVERT_HEAD": "a revert is in progress",
    }
    for marker, label in marks.items():
        if (git_dir / marker).exists():
            raise PreflightError(f"{label}; finish or abort it first")
    for marker in ("rebase-merge", "rebase-apply"):
        if (git_dir / marker).is_dir():
            raise PreflightError("a rebase is in progress; finish or abort it first")
    if (git_dir / "BISECT_LOG").exists():
        raise PreflightError("a bisect is in progress; run `git bisect reset` first")


def dirty_sets(root) -> tuple[set[str], set[str]]:
    """Returns (dirty tracked paths, untracked paths). Rename sources count as dirty."""
    raw = gitcmd.run(root, "status", "--porcelain", "-z", "--untracked-files=normal").stdout
    parts = raw.split(b"\0")
    dirty: set[str] = set()
    untracked: set[str] = set()
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if not entry:
            continue
        text = os.fsdecode(entry)
        xy, path = text[:2], text[3:]
        if xy == "??":
            untracked.add(path)
        else:
            dirty.add(path)
            if xy[0] in ("R", "C") and i < len(parts) and parts[i]:
                dirty.add(os.fsdecode(parts[i]))
                i += 1
    return dirty, untracked


def ls_tree_files(root, sha: str) -> list[str]:
    """All file paths at a commit; submodule entries are skipped."""
    files: list[str] = []
    for entry in gitcmd.null_list(root, "ls-tree", "-r", "-z", sha):
        meta, _, path = entry.partition("\t")
        if not path:
            continue
        fields = meta.split()
        if len(fields) >= 2 and fields[1] == "commit":
            continue
        files.append(path)
    return files


def tree_sizes(root, sha: str) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for entry in gitcmd.null_list(root, "ls-tree", "-r", "-l", "-z", sha):
        meta, _, path = entry.partition("\t")
        if not path:
            continue
        fields = meta.split()
        if len(fields) >= 4 and fields[1] == "blob":
            try:
                sizes[path] = int(fields[3])
            except ValueError:
                pass
    return sizes


def remote_sha(root, remote: str, branch: str, noninteractive: bool = True) -> tuple[bool, str | None, str]:
    """Returns (reachable, sha-or-None, error text)."""
    proc = gitcmd.run(
        root, "ls-remote", "--heads", remote, f"refs/heads/{branch}", check=False, noninteractive=noninteractive
    )
    if proc.returncode != 0:
        return False, None, (proc.stderr or proc.stdout).decode("utf-8", "replace")
    text = proc.stdout.decode("utf-8", "replace").strip()
    return True, (text.split()[0] if text else None), ""


def push_probe(root, facts: Facts, force: bool = False, noninteractive: bool = True) -> str | None:
    """Dry-run push as an auth/permission probe. Returns an error message or None."""
    args = ["push", "--dry-run"]
    if force:
        args.append("--force-with-lease")
    args += [facts.remote, f"HEAD:refs/heads/{facts.branch}"]
    proc = gitcmd.run(root, *args, check=False, noninteractive=noninteractive)
    if proc.returncode == 0:
        return None
    err = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
    low = err.lower()
    if "non-fast-forward" in low or "rejected" in low or "fetch first" in low:
        return "the remote branch has commits you don't have locally — pull/rebase first (or use --force-with-lease)"
    return err[-1500:]


def unpushed(root) -> dict:
    return {
        "stashes": gitcmd.lines(root, "stash", "list"),
        "unpushed": gitcmd.lines(root, "log", "--branches", "--tags", "--not", "--remotes", "--oneline"),
    }


def ensure_excludes(root, git_dir: Path) -> None:
    """Keep gitfreeze artifacts out of git status and out of every push."""
    exclude = Path(git_dir) / "info" / "exclude"
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude.read_text("utf-8") if exclude.exists() else ""
        patterns = [".gitfreeze/", ".gitfreeze.toml", "thaw.sh", "thaw.command", "thaw.cmd"]
        missing = [p for p in patterns if p not in existing.splitlines()]
        if missing:
            with open(exclude, "a", encoding="utf-8") as fh:
                for p in missing:
                    fh.write(p + "\n")
    except OSError:
        pass
