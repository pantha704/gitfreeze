from util import git


def test_version(run_gz, tmp_path):
    r = run_gz(tmp_path, "--version", check=0)
    assert "gitfreeze" in r.stdout


def test_not_a_repo(run_gz, tmp_path):
    r = run_gz(tmp_path, "freeze", check=2)
    assert "not inside a git repository" in r.stderr


def test_no_remote(project, run_gz):
    git(project.work, "remote", "remove", "origin")
    r = run_gz(project.work, "freeze", check=2)
    assert "no git remote" in r.stderr


def test_status_without_data(project, run_gz):
    r = run_gz(project.work, "status", check=0)
    assert "no .gitfreeze data" in r.stdout


def test_status_after_freeze(project, run_gz):
    run_gz(project.work, "freeze", "-y", "--git=keep", check=0)
    r = run_gz(project.work, "status", check=0)
    assert "thaw script present" in r.stdout
    assert "trash records" in r.stdout


def test_undo_without_records(project, run_gz):
    r = run_gz(project.work, "undo", check=1)
    assert "nothing to undo" in r.stderr
