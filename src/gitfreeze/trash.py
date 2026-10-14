"""Trash records: creation, listing, undo, emptying."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from . import fsops
from .errors import GitFreezeError


def trash_dir(root) -> Path:
    return Path(root) / ".gitfreeze" / "trash"


def record_dir(root, record_id: str) -> Path:
    return trash_dir(root) / record_id


def new_record(root, meta: dict) -> Path:
    base = trash_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    d = base / stamp
    n = 1
    while d.exists():
        n += 1
        d = base / f"{stamp}-{n}"
    (d / "files").mkdir(parents=True)
    manifest = {"id": d.name, "status": "in_progress", "files": [], "updated": time.time(), **meta}
    save(d, manifest)
    return d


def load(record_dir_path) -> dict:
    return json.loads((Path(record_dir_path) / "manifest.json").read_text("utf-8"))


def save(record_dir_path, manifest: dict) -> None:
    manifest["updated"] = time.time()
    (Path(record_dir_path) / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def records(root) -> list[dict]:
    base = trash_dir(root)
    out: list[dict] = []
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "manifest.json").exists():
            try:
                out.append(load(d))
            except Exception:
                out.append({"id": d.name, "status": "corrupt", "files": []})
    return out


def undo(root, record_id: str | None = None) -> str:
    candidates = [r for r in records(root) if r.get("status") == "complete" and not r.get("undone")]
    if record_id:
        candidates = [r for r in candidates if r.get("id") == record_id]
        if not candidates:
            raise GitFreezeError(f"no undoable freeze record with id '{record_id}'")
    if not candidates:
        raise GitFreezeError("nothing to undo — no complete freeze record found")
    rec = candidates[-1]
    d = record_dir(root, rec["id"])
    failures: list[str] = []
    restored = 0
    for item in rec.get("files", []):
        rel = item["path"]
        src = d / "files" / rel
        dst = Path(root) / rel
        if os.path.lexists(dst):
            failures.append(f"{rel} (a file already exists there)")
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
            restored += 1
        except OSError as exc:
            failures.append(f"{rel} ({exc})")
    if rec.get("git_dropped"):
        src = d / "dot-git"
        dst = Path(root) / ".git"
        if os.path.lexists(dst):
            failures.append(".git (a .git already exists here)")
        else:
            try:
                os.replace(src, dst)
            except OSError as exc:
                failures.append(f".git ({exc})")
    if failures:
        save(d, rec)
        raise GitFreezeError("undo incomplete:\n  " + "\n  ".join(failures[:20]))
    rec["undone"] = True
    save(d, rec)
    return rec["id"]


def empty(root, record_id: str | None = None) -> tuple[int, int]:
    """Delete trash records. Returns (records_removed, bytes_reclaimed)."""
    recs = records(root)
    if record_id:
        recs = [r for r in recs if r.get("id") == record_id]
    for rec in recs:
        if rec.get("status") == "in_progress":
            raise GitFreezeError(
                f"record {rec.get('id')} is incomplete (a freeze crashed mid-way) — run `gitfreeze undo` first"
            )
    removed = 0
    total = 0
    for rec in recs:
        d = record_dir(root, rec["id"])
        total += fsops.dir_size(d)
        shutil.rmtree(d)
        removed += 1
    if removed and not any(trash_dir(root).iterdir()):
        try:
            trash_dir(root).rmdir()
        except OSError:
            pass
    return removed, total
