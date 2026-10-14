from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from util import base_env, make_project


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


@pytest.fixture
def run_gz():
    def _run(cwd, *args, input=None, env=None, check=None):
        proc = subprocess.run(
            [sys.executable, "-m", "gitfreeze", *[str(a) for a in args]],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            input=input,
            env={**base_env(), **(env or {})},
        )
        if check is not None:
            assert proc.returncode == check, (
                "gitfreeze "
                + " ".join(str(a) for a in args)
                + f" rc={proc.returncode}\n--- stdout ---\n"
                + proc.stdout
                + "\n--- stderr ---\n"
                + proc.stderr
            )
        return proc

    return _run


@pytest.fixture
def run_bash():
    bash = shutil.which("bash")

    def _run(cwd, *args, check=None):
        if not bash:
            pytest.skip("bash is not available on this system")
        proc = subprocess.run(
            [bash, *[str(a) for a in args]],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=base_env(),
        )
        if check is not None:
            assert proc.returncode == check, (
                "bash "
                + " ".join(str(a) for a in args)
                + f" rc={proc.returncode}\n--- stdout ---\n"
                + proc.stdout
                + "\n--- stderr ---\n"
                + proc.stderr
            )
        return proc

    return _run
