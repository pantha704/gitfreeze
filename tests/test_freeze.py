from util import git, read, read_from_git, write


def test_freeze_clean_cycle_and_undo(project, run_gz):
    work = project.work
    write(work / ".env", "SECRET=1\n")
    write(work / "node_modules/pkg/blob.bin", "junk")

    run_gz(work, "freeze", "-y", "--git=drop", check=0)

    assert not (work / ".git").exists()
    assert not (work / "README.md").exists()
    assert not (work / "src/app.py").exists()
    assert read(work / ".env") == "SECRET=1\n"
    assert read(work / "node_modules/pkg/blob.bin") == "junk"
    for name in ("thaw.sh", "thaw.cmd", "thaw.command"):
        assert (work / name).exists(), name
    assert (work / ".gitfreeze" / "trash").is_dir()

    run_gz(work, "undo", check=0)
    assert (work / ".git").is_dir()
    assert read(work / "README.md") == "# demo\n"
    assert read(work / "src/lib/util.py") == "X = 1\n"
    assert read(work / ".env") == "SECRET=1\n"


def test_freeze_aborts_on_dirty_without_flags(project, run_gz):
    write(project.work / "README.md", "# changed\n")
    r = run_gz(project.work, "freeze", "-y", "--git=keep", check=3)
    assert "modified tracked file" in r.stderr
    assert read(project.work / "README.md") == "# changed\n"
    assert not (project.work / "thaw.sh").exists()
    assert not (project.work / ".gitfreeze").exists()


def test_freeze_dirty_keep(project, run_gz):
    work = project.work
    write(work / "README.md", "# changed\n")
    run_gz(work, "freeze", "-y", "--dirty=keep", "--git=keep", check=0)
    assert read(work / "README.md") == "# changed\n"
    assert not (work / "src/app.py").exists()
    status = git(work, "status", "--porcelain").stdout.decode()
    assert "README.md" in status


def test_freeze_dirty_commit_pushes_and_purges(project, run_gz):
    work = project.work
    write(work / "README.md", "# changed\n")
    write(work / "untracked.txt", "new\n")
    run_gz(work, "freeze", "-y", "--dirty=commit", "--git=drop", check=0)

    assert not (work / "README.md").exists()
    assert read(work / "untracked.txt") == "new\n"

    remote_head = git(project.remote, "rev-parse", "main").stdout.decode().strip()
    assert read_from_git(project.remote, remote_head, "README.md") == "# changed\n"
    names = git(project.remote, "ls-tree", "-r", "--name-only", remote_head).stdout.decode().splitlines()
    assert names == ["README.md", "src/app.py", "src/lib/util.py"]
    assert "untracked.txt" not in names


def test_local_config_drives_git_drop(project, run_gz):
    write(project.work / ".gitfreeze.toml", '[freeze]\ngit = "drop"\n')
    run_gz(project.work, "freeze", "-y", check=0)
    assert not (project.work / ".git").exists()
    assert (project.work / "thaw.sh").exists()


def test_freeze_from_subdir(project, run_gz):
    run_gz(project.work / "src", "freeze", "-y", "--git=drop", check=0)
    assert not (project.work / "README.md").exists()
    assert (project.work / "thaw.sh").exists()
    assert not (project.work / "src" / "thaw.sh").exists()


def test_freeze_dry_run_changes_nothing(project, run_gz):
    r = run_gz(project.work, "freeze", "--dry-run", check=0)
    assert "dry-run" in r.stdout
    assert (project.work / "README.md").exists()
    assert not (project.work / "thaw.sh").exists()
    assert not (project.work / ".gitfreeze").exists()


def test_freeze_non_ascii_names(project, run_gz, run_bash):
    work = project.work
    write(work / "süß" / "日本語.txt", "hello\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "unicode")
    git(work, "push")
    run_gz(work, "freeze", "-y", "--git=drop", check=0)
    assert not (work / "süß" / "日本語.txt").exists()
    run_bash(work, "thaw.sh", check=0)
    assert read(work / "süß" / "日本語.txt") == "hello\n"
