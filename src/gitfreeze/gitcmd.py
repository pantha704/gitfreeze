"""Thin, testable wrapper around the git CLI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_HEAD = ["git", "-c", "core.quotepath=false"]


class GitFailure(RuntimeError):
    def __init__(self, args, returncode: int, stderr: str = "", stdout: str = ""):
        self.git_args = list(args)
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        tail = (stderr or stdout or "").strip().splitlines()
        tail = "\n".join(tail[-8:])
        super().__init__(f"git {' '.join(args)} failed (exit {returncode})" + (f":\n{tail}" if tail else ""))


def _env(noninteractive: bool) -> dict:
    env = dict(os.environ)
    if noninteractive:
        env["GIT_TERMINAL_PROMPT"] = "0"
        env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def run(
    cwd,
    *args: str,
    check: bool = True,
    noninteractive: bool = False,
    input: bytes | None = None,
) -> subprocess.CompletedProcess:
    cmd = [*_HEAD, *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=_env(noninteractive),
            capture_output=True,
            input=input,
        )
    except FileNotFoundError as e:
        raise GitFailure(args, 127, f"git not found on PATH: {e}") from e
    if check and proc.returncode != 0:
        raise GitFailure(
            args,
            proc.returncode,
            proc.stderr.decode("utf-8", "replace"),
            proc.stdout.decode("utf-8", "replace"),
        )
    return proc


def out(cwd, *args: str, **kw) -> str:
    return run(cwd, *args, **kw).stdout.decode("utf-8", "replace").strip()


def lines(cwd, *args: str, **kw) -> list[str]:
    return [ln for ln in out(cwd, *args, **kw).splitlines() if ln.strip()]


def null_list(cwd, *args: str, **kw) -> list[str]:
    raw = run(cwd, *args, **kw).stdout
    return [os.fsdecode(part) for part in raw.split(b"\0") if part]


def ok(cwd, *args: str, **kw) -> bool:
    kw.pop("check", None)
    return run(cwd, *args, check=False, **kw).returncode == 0


def version() -> str:
    try:
        return out(Path("."), "--version")
    except Exception:  # pragma: no cover - defensive
        return "unknown"
