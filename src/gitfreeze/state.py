"""Crash markers and the local audit log (.gitfreeze/)."""

from __future__ import annotations

import json
import time
from pathlib import Path


def dir_of(root) -> Path:
    return Path(root) / ".gitfreeze"


def state_path(root) -> Path:
    return dir_of(root) / "state.json"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read(root) -> dict | None:
    path = state_path(root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {"op": "unknown", "phase": "unreadable"}


def begin(root, op: str, **fields) -> None:
    _write(state_path(root), {"op": op, "phase": "started", "ts": time.time(), **fields})


def update(root, **fields) -> None:
    current = read(root) or {}
    current.update(fields)
    _write(state_path(root), current)


def end(root) -> None:
    try:
        state_path(root).unlink()
    except FileNotFoundError:
        pass


def log(root, event: str, **fields) -> None:
    d = dir_of(root)
    d.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), "event": event, **fields}
    with open(d / "log.ndjson", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
