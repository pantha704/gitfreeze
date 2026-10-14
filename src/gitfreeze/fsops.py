"""Filesystem helpers that behave the same on Linux, macOS and Windows."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path


def lexists(path) -> bool:
    """Like os.path.exists but true for broken symlinks too."""
    return os.path.lexists(str(path))


def rmtree(path, ignore_errors: bool = False) -> None:
    """shutil.rmtree that copes with read-only files (git objects are read-only on Windows)."""
    if ignore_errors:
        shutil.rmtree(path, ignore_errors=True)
        return

    if sys.version_info >= (3, 12):

        def _onexc(func, p, exc):
            try:
                os.chmod(p, stat.S_IWRITE)
                func(p)
            except OSError:
                raise exc

        shutil.rmtree(path, onexc=_onexc)
    else:

        def _onerror(func, p, exc_info):
            try:
                os.chmod(p, stat.S_IWRITE)
                func(p)
            except OSError:
                raise exc_info[1]

        shutil.rmtree(path, onerror=_onerror)


def dir_size(path: Path, skip_top: set[str] | None = None) -> int:
    """Recursive size in bytes; skips top-level names in skip_top; never raises."""
    total = 0
    skip_top = skip_top or set()
    stack = [Path(path)]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if current == path and entry.name in skip_top:
                        continue
                    stack.append(Path(entry.path))
                else:
                    total += entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
    return total


def prune_empty_dirs(root: Path) -> None:
    """Remove now-empty directories bottom-up; skips .git and .gitfreeze; never raises."""
    root = Path(root)
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        d = Path(dirpath)
        if d == root:
            continue
        try:
            parts = d.relative_to(root).parts
        except ValueError:
            continue
        if parts and parts[0] in (".git", ".gitfreeze"):
            continue
        try:
            os.rmdir(d)
        except OSError:
            pass
