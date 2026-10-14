import random

import pytest

from util import git, read, write


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_freeze_thaw_roundtrip(seed, project, run_gz, run_bash):
    rng = random.Random(seed)
    work = project.work
    for i in range(rng.randint(15, 30)):
        depth = rng.randint(1, 3)
        parts = [f"d{rng.randint(0, 3)}" for _ in range(depth)]
        name = "/".join(parts + [f"f{i}.txt"])
        content = "".join(rng.choice("abcdefghij\n") for _ in range(rng.randint(10, 200)))
        write(work / name, content)
    git(work, "add", "-A")
    git(work, "commit", "-m", "bulk")
    git(work, "push")

    write(work / ".env", "SECRET=1\n")
    write(work / "node_modules/junk.bin", "junk")
    sha = git(work, "rev-parse", "HEAD").stdout.decode().strip()

    run_gz(work, "freeze", "-y", "--git=drop", check=0)
    assert not (work / ".git").exists()
    run_bash(work, "thaw.sh", check=0)

    names = git(work, "ls-tree", "-r", "--name-only", sha).stdout.decode().splitlines()
    assert names
    for name in names:
        expected = git(work, "show", f"{sha}:{name}").stdout
        assert (work / name).read_bytes() == expected, name
    assert read(work / ".env") == "SECRET=1\n"
    assert read(work / "node_modules/junk.bin") == "junk"
