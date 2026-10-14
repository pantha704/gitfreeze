"""Two-phase purge: rename into trash, roll back cleanly on any failure."""

from __future__ import annotations

import os
from pathlib import Path

from . import fsops


def trash_paths(root: Path, paths: list[str], files_dir: Path) -> tuple[list[dict], list[tuple[str, str]], int]:
    """Move paths into files_dir preserving layout.

    Returns (items_still_in_trash, errors, rolled_back_count). On any error the
    moved items are rolled back; whatever could not be rolled back is returned
    in the first element so it stays recoverable via `gitfreeze undo`.
    """
    root = Path(root)
    moved: list[dict] = []
    errors: list[tuple[str, str]] = []
    for rel in paths:
        src = root / rel
        dst = files_dir / rel
        if not fsops.lexists(src):
            continue  # vanished since the plan was computed; nothing to move
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            size = os.lstat(src).st_size
            os.replace(src, dst)
            moved.append({"path": rel, "size": size})
        except OSError as exc:
            errors.append((rel, str(exc)))
    remaining: list[dict] = []
    if errors:
        for item in reversed(moved):
            try:
                src = root / item["path"]
                src.parent.mkdir(parents=True, exist_ok=True)
                os.replace(files_dir / item["path"], src)
            except OSError:
                remaining.append(item)
        remaining.reverse()
        return remaining, errors, len(moved) - len(remaining)
    return moved, errors, 0


def delete_paths(root: Path, paths: list[str]) -> list[tuple[str, str]]:
    """Hard delete (only used by --trash=off). Returns per-file errors."""
    errors: list[tuple[str, str]] = []
    for rel in paths:
        try:
            os.unlink(Path(root) / rel)
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append((rel, str(exc)))
    return errors
