from util import git, read, write


def test_thaw_script_is_valid_shell(project, run_gz, run_bash):
    run_gz(project.work, "freeze", "-y", "--git=keep", check=0)
    run_bash(project.work, "-n", "thaw.sh", check=0)


def test_thaw_restores_everything(project, run_gz, run_bash):
    work = project.work
    write(work / ".env", "SECRET=local\n")
    sha = git(work, "rev-parse", "HEAD").stdout.decode().strip()
    run_gz(work, "freeze", "-y", "--git=drop", check=0)
    assert not (work / ".git").exists()

    run_bash(work, "thaw.sh", check=0)

    assert (work / ".git").is_dir()
    names = git(work, "ls-tree", "-r", "--name-only", sha).stdout.decode().splitlines()
    assert names
    for name in names:
        expected = git(work, "show", f"{sha}:{name}").stdout
        assert (work / name).read_bytes() == expected, name
    assert read(work / ".env") == "SECRET=local\n"
    status = git(work, "status", "--porcelain").stdout.decode()
    assert "?? .env" in status


def test_thaw_keeps_local_and_saves_duplicate(project, run_gz, run_bash):
    work = project.work
    write(work / "src/lib/util.py", "X = 2  # local edit\n")
    run_gz(work, "freeze", "-y", "--dirty=keep", "--git=drop", check=0)
    assert read(work / "src/lib/util.py") == "X = 2  # local edit\n"
    run_bash(work, "thaw.sh", check=0)
    assert read(work / "src/lib/util.py") == "X = 2  # local edit\n"
    assert read(work / "src/lib/util.py.gitfreeze-new") == "X = 1\n"


def test_thaw_offline_from_local_git(project, run_gz, run_bash):
    work = project.work
    run_gz(work, "freeze", "-y", "--git=keep", check=0)
    assert not (work / "README.md").exists()
    project.remote.rename(project.tmp / "remote-hidden.git")
    run_bash(work, "thaw.sh", check=0)
    assert read(work / "README.md") == "# demo\n"
    assert read(work / "src/lib/util.py") == "X = 1\n"


def test_thaw_twice_is_noop(project, run_gz, run_bash):
    work = project.work
    run_gz(work, "freeze", "-y", "--git=keep", check=0)
    run_bash(work, "thaw.sh", check=0)
    run_bash(work, "thaw.sh", check=0)
    dupes = [p.relative_to(work).as_posix() for p in work.rglob("*.gitfreeze-new")]
    assert not dupes
    assert read(work / "README.md") == "# demo\n"


def test_thaw_at_specific_sha(project, run_gz, run_bash):
    work = project.work
    first = git(work, "rev-parse", "HEAD").stdout.decode().strip()
    write(work / "extra.txt", "v2\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "v2")
    run_gz(work, "freeze", "-y", "--git=drop", check=0)
    run_bash(work, "thaw.sh", "--at", first, check=0)
    assert (work / "README.md").exists()
    assert not (work / "extra.txt").exists()
