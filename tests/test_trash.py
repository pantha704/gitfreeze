def test_trash_list_then_empty(project, run_gz):
    work = project.work
    run_gz(work, "freeze", "-y", "--git=drop", check=0)

    r = run_gz(work, "trash", "list", check=0)
    assert "git_dropped=True" in r.stdout
    assert "complete" in r.stdout

    r = run_gz(work, "trash", "empty", "-y", check=0)
    assert "removed 1 record" in r.stdout

    r = run_gz(work, "undo", check=1)
    assert "nothing to undo" in r.stderr


def test_trash_empty_needs_confirmation_in_non_tty(project, run_gz):
    run_gz(project.work, "freeze", "-y", "--git=drop", check=0)
    r = run_gz(project.work, "trash", "empty", check=3)
    assert "declined" in r.stderr
