# Ported from crapper's tests/test_coverage.py (its Kover cases) and tests/test_cli.py (its --coverage-report cases).
import pytest

from dreck.cli import run
from helpers import commit_all, scores, write


def kover(classes: dict[str, list[tuple[str, int, int]]]) -> str:
    """A Kover XML report: `classes` maps `pkg/Class` to (method, missed, covered) rows, no lines."""

    body = "".join(
        f'<class name="{name}" sourcefilename="Board.kt">'
        + "".join(
            f'<method name="{method}" desc="()V">'
            f'<counter type="INSTRUCTION" missed="{missed}" covered="{covered}"/>'
            f'<counter type="LINE" missed="9" covered="9"/></method>'
            for method, missed, covered in methods
        )
        + "</class>"
        for name, methods in classes.items()
    )
    return f'<?xml version="1.0" ?><report name="Kover"><package name="demo">{body}</package></report>'


BOARD = """\
package demo

fun place(x: Int): Int {
    return x
}

class Board {
    fun tick(): Int {
        return 1
    }

    fun show(a: Int) {
    }

    fun show(a: String) {
    }

    fun clear() {
    }

    class Cell {
        fun mark(on: Boolean) {
            if (on) println("x")
        }
    }
}
"""


@pytest.fixture
def board(tmp_path, monkeypatch):
    write(tmp_path, "app/src/main/kotlin/demo/Board.kt", BOARD)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_given_methods_named_after_a_function_when_scoring_then_their_counts_add_up(board, capsys):
    write(
        board,
        "build/reports/kover/report.xml",
        kover(
            {
                "demo/BoardKt": [("place", 1, 3)],
                "demo/Board": [
                    ("tick-Xk2a9", 4, 0),
                    ("tick$lambda$0", 0, 2),
                    ("tick$default", 0, 2),
                    ("ticker", 0, 100),
                    ("show", 1, 1),
                    ("show", 0, 2),
                ],
                "demo/Board$Cell": [("mark", 1, 1)],
            }
        ),
    )

    assert run(["--coverage-report", "build/reports/kover/report.xml"]) == 0

    captured = capsys.readouterr()
    assert scores(captured.out) == {
        ("place", 3): ("75.0%", "1.0"),
        ("tick", 8): ("50.0%", "1.1"),
        ("show", 12): ("75.0%", "1.0"),
        ("show", 15): ("75.0%", "1.0"),
        ("clear", 18): ("0.0%", "2.0"),
        ("mark", 22): ("50.0%", "2.5"),
    }
    assert len(captured.err.splitlines()) == 1


def test_given_a_class_absent_from_the_report_when_scoring_then_its_function_scores_zero(board, capsys):
    # The file's top-level class is in the report, so Kotlin is covered and not unmeasured.
    write(
        board,
        "report.xml",
        kover({"demo/BoardKt": [("helper", 0, 5)], "demo/Other": [("place", 0, 5), ("tick", 0, 5)]}),
    )

    assert run(["--coverage-report", "report.xml"]) == 0

    captured = capsys.readouterr()
    assert {coverage for coverage, _crap in scores(captured.out).values()} == {"0.0%"}
    assert len(captured.err.splitlines()) == 1


def test_given_reports_by_path_when_scoring_then_they_add_up_and_each_file_is_read_once(board, capsys):
    write(board, "reports/top.xml", kover({"demo/BoardKt": [("place", 0, 4)]}))
    write(board, "reports/app/kover.data", kover({"demo/Board": [("tick", 1, 1)]}))
    write(board, "reports/notes.txt", "not a report\n")
    write(board, "feature/report.xml", kover({"demo/Board": [("clear", 3, 1)]}))

    assert run(["--coverage-report", "reports", "--coverage-report", "reports/top.xml", "--coverage-report", str(board / "feature")]) == 0

    found = scores(capsys.readouterr().out)
    assert found[("place", 3)][0] == "100.0%"
    assert found[("tick", 8)][0] == "50.0%"
    assert found[("clear", 18)][0] == "25.0%"


def test_given_a_jacoco_report_with_a_doctype_when_scoring_then_it_is_read(board, capsys):
    write(
        board,
        "jacoco.xml",
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">'
        '<report name="demo"><package name="demo"><class name="demo/Board">'
        '<method name="tick" desc="()I" line="8">'
        '<counter type="INSTRUCTION" missed="0" covered="4"/></method>'
        "</class></package></report>",
    )

    assert run(["--coverage-report", "jacoco.xml"]) == 0

    assert scores(capsys.readouterr().out)[("tick", 8)] == ("100.0%", "1.0")


@pytest.mark.parametrize("given", ["missing", "empty", "notes.txt"])
def test_given_a_report_path_missing_or_without_report_when_running_then_the_run_stops(board, capsys, given):
    (board / "empty").mkdir()
    write(board, "empty/notes.txt", "not a report\n")
    write(board, "notes.txt", "not a report\n")

    assert run(["--coverage-report", given]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"dreck: --coverage-report {given}: ")
    assert len(captured.err.splitlines()) == 1


def test_given_a_damaged_report_when_running_then_named_it_stops_and_in_a_folder_it_is_skipped(board, capsys):
    damaged = '<?xml version="1.0"?><!DOCTYPE report><report name="demo"><pack'
    write(board, "reports/half.xml", damaged)
    write(board, "reports/good.xml", kover({"demo/Board": [("tick", 0, 2)]}))
    write(board, "broken/half.xml", damaged)

    assert run(["--coverage-report", "reports/half.xml"]) == 1
    alone = capsys.readouterr()
    assert run(["--coverage-report", "reports", "--coverage-report", "reports/half.xml"]) == 1
    folder_then_file = capsys.readouterr()
    assert run(["--coverage-report", "broken"]) == 1
    only_damaged = capsys.readouterr()
    assert run(["--coverage-report", "reports"]) == 0
    in_folder = capsys.readouterr()

    assert alone.out == folder_then_file.out == only_damaged.out == ""
    assert alone.err.startswith("dreck: --coverage-report reports/half.xml: unreadable JaCoCo or Kover report (")
    assert "skipped" not in alone.err
    assert "dreck: --coverage-report reports/half.xml: unreadable JaCoCo or Kover report (" in folder_then_file.err
    assert only_damaged.err.splitlines()[-1].startswith("dreck: --coverage-report broken: holds no coverage report")
    assert in_folder.err.startswith("dreck: reports/half.xml: unreadable JaCoCo or Kover report (")
    assert in_folder.err.splitlines()[0].endswith("; skipped.")
    assert scores(in_folder.out)[("tick", 8)][0] == "100.0%"
    assert "Traceback" not in alone.err + folder_then_file.err + only_damaged.err + in_folder.err


def test_given_a_missing_report_and_no_file_when_running_then_the_report_is_not_read(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert run(["--coverage-report", "missing"]) == 0

    assert capsys.readouterr().out == "No source files to analyze.\n"


def test_given_a_language_no_report_covers_when_running_then_it_prints_dashes_and_one_hint(board, stand_in, capsys):
    write(board, "lines/One.si", "first\nsecond\n")
    write(board, "lines/Two.sin", "third\n")
    write(board, "report.xml", kover({"demo/Board": [("tick", 0, 2)]}))

    assert run(["--coverage-report", "report.xml"]) == 0

    captured = capsys.readouterr()
    found = scores(captured.out)
    assert found[("tick", 8)] == ("100.0%", "1.0")
    assert found[("clear", 18)] == ("0.0%", "2.0")
    assert found[("first", 1)] == found[("second", 2)] == found[("third", 1)] == ("-", "-")
    err = captured.err.splitlines()
    assert err[:-1] == [
        "dreck: Standin: coverage and CRAP show -; no coverage report given matches its files. "
        "Pass --coverage-report <a stand-in report>."
    ]


def test_given_no_report_when_running_then_no_hint_is_printed(board, stand_in, capsys):
    write(board, "lines/One.si", "first\n")

    assert run([]) == 0

    captured = capsys.readouterr()
    assert {score for score in scores(captured.out).values()} == {("-", "-")}
    assert len(captured.err.splitlines()) == 1
    assert captured.err.startswith("dreck: 2 files scanned")


def test_given_a_report_matching_no_function_when_running_then_a_warning_names_it(board, capsys):
    write(board, "other.xml", kover({"other/Thing": [("tick", 0, 2)]}))
    write(board, "report.xml", kover({"demo/Board": [("tick", 0, 2)]}))

    assert run(["--coverage-report", "other.xml", "--coverage-report", "report.xml"]) == 0

    captured = capsys.readouterr()
    assert scores(captured.out)[("tick", 8)][0] == "100.0%"
    assert captured.err.splitlines()[:-1] == [
        "dreck: --coverage-report other.xml: matches none of the files being scored; "
        "was it made in another checkout or for another project?"
    ]

    assert run(["--coverage-report", "other.xml"]) == 0

    captured = capsys.readouterr()
    assert {score for score in scores(captured.out).values()} == {("-", "-")}
    assert captured.err.splitlines()[:-1] == [
        "dreck: --coverage-report other.xml: matches none of the files being scored; "
        "was it made in another checkout or for another project?",
        "dreck: Kotlin: coverage and CRAP show -; no coverage report given matches its files. "
        "Pass --coverage-report <Kover's XML report>.",
    ]


def test_given_a_changed_file_missing_from_the_report_when_running_with_changed_functions_then_the_warning_names_the_change(
    board, capsys
):
    write(board, "report.xml", kover({"demo/Board": [("tick", 0, 2)]}))
    commit_all(board)
    write(board, "app/src/main/kotlin/demo/Other.kt", "package demo\n\nclass Other {\n    fun tick() {\n    }\n}\n")

    assert run(["--changed-functions", "--coverage-report", "report.xml"]) == 0

    captured = capsys.readouterr()
    assert captured.err.splitlines()[:-1] == [
        "dreck: --coverage-report report.xml: matches none of the files being scored; "
        "was it made in another checkout or for another project, or before the files changed?",
        "dreck: Kotlin: coverage and CRAP show -; no coverage report given matches its files. "
        "Pass --coverage-report <Kover's XML report>.",
    ]


def test_given_files_without_functions_when_running_with_a_report_then_nothing_warns(tmp_path, capsys, monkeypatch):
    write(tmp_path, "Empty.kt", "package demo\n")
    write(tmp_path, "other.xml", kover({"other/Thing": [("tick", 0, 2)]}))
    monkeypatch.chdir(tmp_path)

    assert run(["--coverage-report", "other.xml"]) == 0

    assert len(capsys.readouterr().err.splitlines()) == 1


def test_given_no_path_after_coverage_report_when_running_then_it_exits_1(capsys):
    assert run(["--coverage-report"]) == 1

    assert capsys.readouterr().err.startswith("--coverage-report needs a path\n\nUsage: dreck")
