# Copied from doppel's tests/test_changed.py.
from dreck.changed import changed_lines
from helpers import commit_all, git, write

BEFORE = "one\ntwo\nthree\nfour\nfive\n"


def test_given_an_edited_tracked_file_when_read_then_only_its_edited_lines_are_changed(tmp_path):
    write(tmp_path, "a.kt", BEFORE)
    write(tmp_path, "same.kt", BEFORE)
    commit_all(tmp_path)
    write(tmp_path, "a.kt", "one\nTWO\nthree\nfour\nfive\nsix\n")

    assert changed_lines(tmp_path) == {(tmp_path / "a.kt").resolve(): {2, 6}}


def test_given_deleted_lines_when_read_then_the_line_above_them_is_changed(tmp_path):
    write(tmp_path, "a.kt", BEFORE)
    commit_all(tmp_path)
    write(tmp_path, "a.kt", "one\ntwo\nfive\n")

    assert changed_lines(tmp_path) == {(tmp_path / "a.kt").resolve(): {2}}


def test_given_an_untracked_file_when_read_then_every_line_is_changed(tmp_path):
    write(tmp_path, "a.kt", BEFORE)
    commit_all(tmp_path)
    write(tmp_path, "new/b.kt", BEFORE)

    assert changed_lines(tmp_path) == {(tmp_path / "new/b.kt").resolve(): None}


def test_given_no_commit_yet_when_read_then_every_line_of_each_file_is_changed(tmp_path):
    write(tmp_path, "a.kt", BEFORE)
    write(tmp_path, "b.kt", BEFORE)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "a.kt")

    assert changed_lines(tmp_path) == {(tmp_path / "a.kt").resolve(): None, (tmp_path / "b.kt").resolve(): None}
