"""Shared helpers for the test-suite (git plumbing on throwaway repos)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"

_CFG_DIR = Path(tempfile.mkdtemp(prefix="gitfreeze-tests-"))
_GITCONFIG = _CFG_DIR / "gitconfig"
_GITCONFIG.write_text(
    "[core]\n\tautocrlf = false\n\tquotepath = false\n[init]\n\tdefaultBranch = main\n",
    encoding="utf-8",
)


def base_env() -> dict:
    env = dict(os.environ)
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_GLOBAL": str(_GITCONFIG),
            "GIT_CONFIG_NOSYSTEM": "1",
            "PYTHONPATH": str(SRC),
            "PYTHONIOENCODING": "utf-8",
            "NO_COLOR": "1",
            "XDG_CONFIG_HOME": str(_CFG_DIR / "xdg"),
            "APPDATA": str(_CFG_DIR / "xdg"),
        }
    )
    return env


def git(cwd, *args, check=True, input=None) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *[str(a) for a in args]],
        cwd=str(cwd),
        capture_output=True,
        input=input,
        env=base_env(),
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            "git "
            + " ".join(str(a) for a in args)
            + " failed:\n"
            + proc.stderr.decode("utf-8", "replace")
            + proc.stdout.decode("utf-8", "replace")
        )
    return proc


def write(path, content) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)


def read(path) -> str:
    return Path(path).read_bytes().decode("utf-8")


def read_from_git(cwd, sha: str, path: str) -> str:
    return git(cwd, "show", f"{sha}:{path}").stdout.decode("utf-8")


def make_project(tmp_path) -> SimpleNamespace:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    work = tmp_path / "work"
    git(tmp_path, "init", "-b", "main", str(work))
    for key, value in (
        ("user.email", "test@example.com"),
        ("user.name", "Test"),
        ("core.autocrlf", "false"),
        ("commit.gpgsign", "false"),
    ):
        git(work, "config", key, value)
    write(work / "README.md", "# demo\n")
    write(work / "src/app.py", "print('hello')\n")
    write(work / "src/lib/util.py", "X = 1\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "initial")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-u", "origin", "main")
    return SimpleNamespace(work=work, remote=remote, tmp=tmp_path)
