"""Pre-push scans: secret-like content, suspicious file names, big files, LFS."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from . import gitcmd

# Strong patterns: a hit blocks the freeze outright (no override).
STRONG: list[tuple[str, re.Pattern]] = [
    ("PRIVATE KEY block", re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained PAT", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI-style key", re.compile(rb"\bsk-(?:proj-|live-)?[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(rb"\bAIza[0-9A-Za-z_\-]{35}\b")),
]

SUSPICIOUS_NAMES = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "credentials.json",
    ".netrc",
    "*.p12",
    "*.pfx",
    "*.jks",
]

_SCAN_LIMIT = 2 * 1024 * 1024  # do not read more than 2 MiB of any one file


def suspicious_name(path: str) -> bool:
    base = Path(path).name.lower()
    return any(fnmatch.fnmatch(base, pat) for pat in SUSPICIOUS_NAMES)


def outgoing_paths(root, remote_sha: str | None, commit_limit: int = 50) -> list[str]:
    """Files that the upcoming push would send."""
    known = False
    commits: list[str] = []
    if remote_sha:
        proc = gitcmd.run(root, "rev-list", "--max-count=200", f"{remote_sha}..HEAD", check=False)
        if proc.returncode == 0:
            known = True
            commits = proc.stdout.decode("utf-8", "replace").split()
    if not known:
        commits = gitcmd.lines(root, "rev-list", "-n", "20", "HEAD")
    names: list[str] = []
    seen: set[str] = set()
    for commit in commits[:commit_limit]:
        proc = gitcmd.run(root, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", commit, check=False)
        for raw in proc.stdout.split(b"\0"):
            name = os.fsdecode(raw) if raw else ""
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def scan_tracked_names(root) -> list[str]:
    tracked = gitcmd.null_list(root, "ls-files", "-z")
    return [f for f in tracked if suspicious_name(f)]


def scan_committable_content(root, paths) -> list[str]:
    """Scan files as they are on disk (for --dirty=commit preview)."""
    hits: list[str] = []
    for rel in paths:
        path = Path(root) / rel
        try:
            if not path.is_file():
                continue
            with open(path, "rb") as fh:
                data = fh.read(_SCAN_LIMIT)
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        for label, rx in STRONG:
            if rx.search(data):
                hits.append(f"{rel}: {label}")
                break
    return hits


def scan_outgoing_content(root, paths) -> tuple[list[str], list[str]]:
    """Scan HEAD content of outgoing paths. Returns (blockers, unscanned_large)."""
    blockers: list[str] = []
    unscanned: list[str] = []
    for rel in paths:
        size_proc = gitcmd.run(root, "cat-file", "-s", f"HEAD:{rel}", check=False)
        if size_proc.returncode != 0:
            continue  # deleted in HEAD
        try:
            size = int(size_proc.stdout.decode().strip() or "0")
        except ValueError:
            size = 0
        if size > _SCAN_LIMIT:
            unscanned.append(rel)
            continue
        proc = gitcmd.run(root, "show", f"HEAD:{rel}", check=False)
        if proc.returncode != 0:
            continue
        data = proc.stdout[:_SCAN_LIMIT]
        if b"\0" in data[:8192]:
            continue
        for label, rx in STRONG:
            if rx.search(data):
                blockers.append(f"{rel}: {label}")
                break
    return blockers, unscanned


def detect_lfs(root) -> bool:
    for rel in gitcmd.null_list(root, "ls-files", "-z"):
        if not rel.endswith(".gitattributes"):
            continue
        proc = gitcmd.run(root, "show", f"HEAD:{rel}", check=False)
        if proc.returncode == 0 and b"filter=lfs" in proc.stdout:
            return True
    return False
