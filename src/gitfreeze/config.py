"""Configuration: defaults < global config < per-folder config; flags override everything."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "freeze.git": "ask",  # ask | keep | drop
    "freeze.dirty": "ask",  # ask | commit | keep | abort
    "freeze.trash": "keep",  # keep | empty | off
    "freeze.message": "",  # commit message template for --dirty=commit
    "freeze.prune_empty_dirs": False,
    "freeze.warn_file_mb": 50,
    "freeze.max_file_mb": 100,
}


def global_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "gitfreeze" / "config.toml"


def local_path(root: Path) -> Path:
    return Path(root) / ".gitfreeze.toml"


def _flatten(d: dict, prefix: str = "") -> dict:
    flat: dict = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(_flatten(v, f"{key}."))
        else:
            flat[key] = v
    return flat


def _read(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return _flatten(tomllib.load(fh))
    except FileNotFoundError:
        return {}
    except Exception:
        # A corrupt config must not brick the tool; treat as absent but do not hide it silently.
        print(f"warning: ignoring unreadable config {path}", file=sys.stderr)
        return {}


def load(root) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_read(global_path()))
    cfg.update(_read(local_path(root)))
    return cfg


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    text = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def set_local(root, key: str, value) -> None:
    """Persist a single flat key (e.g. 'freeze.git') into the folder-local config."""
    path = local_path(root)
    flat = _read(path)
    flat[key] = value
    sections: dict[str, dict] = {}
    for k, v in flat.items():
        if "." in k:
            section, name = k.split(".", 1)
        else:
            section, name = "", k
        sections.setdefault(section, {})[name] = v
    lines: list[str] = []
    for section in sorted(sections):
        if section:
            lines.append(f"[{section}]")
        for k in sorted(sections[section]):
            lines.append(f"{k} = {_toml_value(sections[section][k])}")
        if section:
            lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
