import os

import pytest

from util import git, write


def test_secret_like_content_blocks_push(project, run_gz):
    work = project.work
    write(work / "keys.txt", "AKIAABCDEFGHIJKLMNOP\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "oops")
    r = run_gz(work, "freeze", "-y", "--git=keep", check=2)
    assert "AWS access key id" in r.stderr
    assert (work / "keys.txt").exists()
    assert not (work / "thaw.sh").exists()
    local = git(work, "rev-parse", "HEAD").stdout.decode().strip()
    remote = git(project.remote, "rev-parse", "main").stdout.decode().strip()
    assert local != remote


def test_big_file_blocks(project, run_gz):
    work = project.work
    write(work / "big.bin", b"x" * (2 * 1024 * 1024))
    git(work, "add", "big.bin")
    git(work, "commit", "-m", "big")
    write(work / ".gitfreeze.toml", "[freeze]\nmax_file_mb = 1\n")
    r = run_gz(work, "freeze", "-y", "--git=keep", check=2)
    assert "over 1 MiB" in r.stderr
    assert (work / "big.bin").exists()


def test_drop_git_refused_with_stash(project, run_gz):
    work = project.work
    write(work / "README.md", "stash me\n")
    git(work, "stash", "push", "-m", "wip")
    r = run_gz(work, "freeze", "-y", "--git=drop", check=6)
    assert "stash" in r.stderr.lower()
    assert (work / ".git").exists()
    assert (work / "README.md").exists()


def test_push_rejected_prevents_purge(project, run_gz):
    if os.name == "nt":
        pytest.skip("server-hook test is POSIX-only")
    work = project.work
    hook = project.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    write(work / "README.md", "# v2\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "v2")
    r = run_gz(work, "freeze", "-y", "--git=keep", check=4)
    assert "push failed" in r.stderr
    assert (work / "README.md").exists()
    assert not (work / "thaw.sh").exists()


def test_suspicious_name_warns_but_proceeds(project, run_gz):
    work = project.work
    write(work / ".env.example", "SAFE=1\n")
    git(work, "add", ".env.example")
    git(work, "commit", "-m", "env example")
    git(work, "push")
    r = run_gz(work, "freeze", "-y", "--git=keep", check=0)
    assert "secret-ish names" in r.stderr
    assert not (work / ".env.example").exists()
