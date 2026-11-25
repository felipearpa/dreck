# Adapted from doppel's tests/test_cli.py.
import os
import re
import shutil
from pathlib import Path

import pytest

from dreck.cli import run
from helpers import commit_all, scores, write

CHOOSE = """\
package demo

fun choose(a: Int?, items: List<Int>): Int {
    if (a == null) return 0
    for (item in items) {}
    return items.firstOrNull() ?: 0
}

fun plain() {
    println("x")
}
"""

LINE = re.compile(r"crap -  cc (\d+)  cov -  (\S+):(\d+)-(\d+)  (.+)")


def listed(out: str) -> list[tuple[int, str, str]]:
    """Complexity, location and name of each printed line; every line is unscored."""

    rows = []
    for line in out.splitlines():
        found = LINE.fullmatch(line)
        assert found, line
        rows.append((int(found[1]), f"{found[2]}:{found[3]}-{found[4]}", found[5]))
    return rows


def summary(err: str) -> str:
    return re.sub(r"\d+\.\d\ds$", "<time>", err.splitlines()[-1])


def test_given_no_report_when_running_then_one_labelled_line_per_function_prints_most_complex_first(tmp_path, capsys, monkeypatch):
    write(tmp_path, "app/src/main/kotlin/Choose.kt", CHOOSE)
    write(tmp_path, "app/src/main/kotlin/Other.kt", "fun other() = if (true) 1 else 2\n")
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0

    captured = capsys.readouterr()
    assert listed(captured.out) == [
        (4, "app/src/main/kotlin/Choose.kt:3-7", "choose"),
        (2, "app/src/main/kotlin/Other.kt:1-1", "other"),
        (1, "app/src/main/kotlin/Choose.kt:9-11", "plain"),
    ]
    assert len(captured.err.splitlines()) == 1
    assert summary(captured.err) == "dreck: 2 files scanned, 3 functions scored, 0 files with parse errors, <time>"


def test_given_paths_and_fragments_when_running_then_they_select_the_files(tmp_path, capsys, monkeypatch):
    for name in ["orders/OrderA.kt", "orders/OrderB.kt", "users/User.kt"]:
        write(tmp_path, name, f"fun {name.split('/')[1][:-3].lower()}() {{}}\n")
    monkeypatch.chdir(tmp_path)

    def files(*args: str) -> list[str]:
        assert run(list(args)) == 0
        return sorted(location.split(":")[0] for _cc, location, _name in listed(capsys.readouterr().out))

    assert files("orders") == ["orders/OrderA.kt", "orders/OrderB.kt"]
    assert files("orders/OrderA.kt", "users") == ["orders/OrderA.kt", "users/User.kt"]
    assert files("User", "OrderB") == ["orders/OrderB.kt", "users/User.kt"]
    assert files(str(tmp_path / "users")) == ["users/User.kt"]


def test_given_a_folder_outside_the_current_directory_when_running_then_paths_print_absolute(tmp_path, capsys, monkeypatch):
    write(tmp_path, "other/Far.kt", "fun far() {}\n")
    (tmp_path / "here").mkdir()
    monkeypatch.chdir(tmp_path / "here")

    assert run([str(tmp_path / "other")]) == 0

    assert listed(capsys.readouterr().out) == [(1, f"{(tmp_path / 'other/Far.kt').resolve()}:1-1", "far")]


def test_given_no_source_file_when_running_then_it_says_so_and_exits_0(tmp_path, capsys, monkeypatch):
    write(tmp_path, "app/Main.kt", "fun main() {}\n")
    monkeypatch.chdir(tmp_path / "app")

    assert run([tmp_path.name]) == 0
    assert capsys.readouterr().out == "No source files to analyze.\n"
    assert run(["Missing.kt"]) == 0
    assert capsys.readouterr().out == "No source files to analyze.\n"


def test_given_test_code_named_when_running_then_it_is_scored(tmp_path, capsys, monkeypatch):
    write(tmp_path, "src/main/kotlin/Orders.kt", "fun orders() {}\n")
    write(tmp_path, "src/test/kotlin/OrdersTest.kt", "fun ordersWork() {}\n")
    write(tmp_path, "src/test/kotlin/Fixtures.kt", "fun fixture() {}\n")
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0
    assert [name for _cc, _location, name in listed(capsys.readouterr().out)] == ["orders"]

    assert run(["src/main", "src/test/kotlin/OrdersTest.kt"]) == 0
    assert [name for _cc, _location, name in listed(capsys.readouterr().out)] == ["orders", "ordersWork"]

    # Inside a named folder, a file ending in `Test.kt` is still skipped.
    assert run(["src/test"]) == 0
    assert [name for _cc, _location, name in listed(capsys.readouterr().out)] == ["fixture"]


def test_given_a_bad_option_when_running_then_it_exits_1_with_the_reason_and_help(capsys):
    assert run(["--verbose"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Unknown option: --verbose\n\nUsage: dreck")


def test_given_a_broken_file_when_running_then_it_is_named_and_still_scored(tmp_path, capsys, monkeypatch):
    write(tmp_path, "Orders.kt", "fun orders() {}\n")
    write(tmp_path, "Broken.kt", "fun kept() {}\n\nfun broken( {\n    val x =\n}\n")
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0

    captured = capsys.readouterr()
    assert "Orders.kt:1-1" in [location for _cc, location, _name in listed(captured.out)]
    assert "kept" in [name for _cc, _location, name in listed(captured.out)]
    err = captured.err.splitlines()
    assert err[0] == "dreck: Broken.kt has parse errors; scored as parsed"
    assert len(err) == 2
    assert re.fullmatch(r"dreck: 2 files scanned, \d+ functions? scored, 1 file with parse errors, <time>", summary(captured.err))


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file chmod 000 denies")
def test_given_an_unreadable_file_when_running_then_it_is_skipped_with_a_warning(tmp_path, capsys, monkeypatch):
    write(tmp_path, "Orders.kt", "fun orders() {}\n")
    write(tmp_path, "Locked.kt", "fun locked() {}\n")
    (tmp_path / "Locked.kt").chmod(0)
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0

    captured = capsys.readouterr()
    assert listed(captured.out) == [(1, "Orders.kt:1-1", "orders")]
    err = captured.err.splitlines()
    assert err[0] == "dreck: Locked.kt cannot be read; skipped"
    assert summary(captured.err) == "dreck: 1 file scanned, 1 function scored, 0 files with parse errors, <time>"


def test_when_running_then_no_file_is_written(tmp_path, capsys, monkeypatch):
    write(tmp_path, "src/main/kotlin/Choose.kt", CHOOSE)
    before = sorted(path for path in tmp_path.rglob("*"))
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0

    assert len(listed(capsys.readouterr().out)) == 2
    assert sorted(path for path in tmp_path.rglob("*")) == before


def test_when_asking_for_help_then_it_lists_the_languages_and_exit_codes(capsys):
    assert run(["--help"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("Usage: dreck [options] [path-or-fragment ...]\n")
    assert "Languages: F# (.fs .fsx), Kotlin (.kt), Swift (.swift).\n" in out
    assert "  0  the run finished\n" in out


def test_given_an_extra_language_file_when_asking_for_help_then_it_is_listed(stand_in, capsys):
    assert run(["--help"]) == 0

    assert "Languages: F# (.fs .fsx), Kotlin (.kt), Standin (.si .sin), Swift (.swift)." in capsys.readouterr().out


ORDERS = """\
fun total(a: Int?): Int {
    if (a == null) return 0
    return a
}

fun plain() {
    println("x")
}
"""


def edited_repository(root: Path) -> None:
    """A repository whose `app` folder has one edit in `plain` of `Orders.kt`,
    one in a test file, and whose `other` folder has one more."""

    write(root, "app/src/main/kotlin/Orders.kt", ORDERS)
    write(root, "app/src/main/kotlin/Kept.kt", "fun kept() {}\n")
    write(root, "app/src/test/kotlin/OrdersTest.kt", "fun ordersWork() {}\n")
    write(root, "other/Far.kt", "fun far() {}\n")
    commit_all(root)
    write(root, "app/src/main/kotlin/Orders.kt", ORDERS.replace('"x"', '"y"'))
    write(root, "app/src/test/kotlin/OrdersTest.kt", "fun ordersStillWork() {}\n")
    write(root, "other/Far.kt", "fun farther() {}\n")


def test_given_changes_in_and_out_of_the_folder_when_running_with_changed_then_only_its_changed_files_kept_by_the_skips_are_scored(tmp_path, capsys, monkeypatch):
    edited_repository(tmp_path)
    monkeypatch.chdir(tmp_path / "app")

    assert run(["--changed"]) == 0

    captured = capsys.readouterr()
    assert listed(captured.out) == [
        (2, "src/main/kotlin/Orders.kt:1-4", "total"),
        (1, "src/main/kotlin/Orders.kt:6-8", "plain"),
    ]
    assert summary(captured.err) == "dreck: 1 file scanned, 2 functions scored, 0 files with parse errors, <time>"


def test_given_changes_in_and_out_of_the_folder_when_running_with_changed_functions_then_only_the_functions_holding_a_changed_line_are_listed(tmp_path, capsys, monkeypatch):
    edited_repository(tmp_path)
    write(tmp_path, "app/src/main/kotlin/New.kt", "fun first() {}\n\nfun second() {}\n")
    monkeypatch.chdir(tmp_path / "app")

    assert run(["--changed-functions"]) == 0

    captured = capsys.readouterr()
    assert listed(captured.out) == [
        (1, "src/main/kotlin/New.kt:1-1", "first"),
        (1, "src/main/kotlin/New.kt:3-3", "second"),
        (1, "src/main/kotlin/Orders.kt:6-8", "plain"),
    ]
    assert summary(captured.err) == "dreck: 2 files scanned, 3 functions scored, 0 files with parse errors, <time>"


def test_given_an_edit_outside_every_function_when_running_with_changed_functions_then_nothing_is_listed(tmp_path, capsys, monkeypatch):
    write(tmp_path, "Orders.kt", ORDERS)
    commit_all(tmp_path)
    write(tmp_path, "Orders.kt", "// Totals.\n" + ORDERS)
    monkeypatch.chdir(tmp_path)

    assert run(["--changed-functions"]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert summary(captured.err) == "dreck: 1 file scanned, 0 functions scored, 0 files with parse errors, <time>"


@pytest.mark.parametrize("option", ["--changed", "--changed-functions"])
def test_given_a_clean_tree_and_a_missing_report_when_running_with_a_git_option_then_nothing_is_analyzed_and_it_exits_0(option, tmp_path, capsys, monkeypatch):
    write(tmp_path, "Orders.kt", ORDERS)
    commit_all(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert run([option, "--coverage-report", "missing/report.xml"]) == 0
    assert capsys.readouterr().out == "No source files to analyze.\n"


@pytest.mark.parametrize("option", ["--changed", "--changed-functions"])
def test_given_no_git_repository_when_running_with_a_git_option_then_it_exits_1_naming_the_option(option, tmp_path, capsys, monkeypatch):
    write(tmp_path, "Orders.kt", ORDERS)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    assert run([option]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"dreck: {option} needs git")
    assert "not a git repository" in captured.err


def test_given_a_change_in_another_repository_when_running_with_changed_functions_on_it_then_git_is_asked_there(tmp_path, capsys, monkeypatch):
    write(tmp_path, "repo/Orders.kt", ORDERS)
    commit_all(tmp_path / "repo")
    write(tmp_path, "repo/Orders.kt", ORDERS.replace("return a\n", "return a + 1\n"))
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    assert run(["--changed-functions", "../repo"]) == 0
    assert listed(capsys.readouterr().out) == [(2, f"{(tmp_path / 'repo/Orders.kt').resolve()}:1-4", "total")]


def test_given_a_report_when_running_with_changed_functions_then_the_edited_function_keeps_the_full_runs_numbers(tmp_path, capsys, monkeypatch):
    fixtures = Path(__file__).parent / "fixtures/kotlin"
    shutil.copy(fixtures / "Orders.kt", tmp_path / "Orders.kt")
    shutil.copy(fixtures / "kover.xml", tmp_path / "kover.xml")
    commit_all(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run(["--coverage-report", "kover.xml"]) == 0
    full = scores(capsys.readouterr().out)
    write(tmp_path, "Orders.kt", (fixtures / "Orders.kt").read_text().replace('"one"', '"single"'))

    assert run(["--changed-functions", "--coverage-report", "kover.xml"]) == 0

    assert scores(capsys.readouterr().out) == {("label", 10): full[("label", 10)]}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("fun total(a: Int?): Int {", (2, "Orders.kt:1-4", "total")),
        ("    return a\n}", (2, "Orders.kt:1-4", "total")),
    ],
)
def test_given_an_edit_on_a_functions_first_or_last_line_when_running_with_changed_functions_then_it_is_listed(line, expected, tmp_path, capsys, monkeypatch):
    write(tmp_path, "Orders.kt", ORDERS)
    commit_all(tmp_path)
    write(tmp_path, "Orders.kt", ORDERS.replace(line, line + " // edited", 1))
    monkeypatch.chdir(tmp_path)

    assert run(["--changed-functions"]) == 0
    assert listed(capsys.readouterr().out) == [expected]
