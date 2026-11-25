# Ported from crapper's tests/test_coverage.py and tests/test_cli.py: their Cobertura cases.
from pathlib import Path

import pytest

from dreck.cli import run
from dreck.coverage import BY_FILE_LINES, load
from dreck.model import Function
from helpers import scores, write


def cobertura(filename, lines, name="Demo.Board"):
    """One Cobertura report with one class, byte-order mark first, as `dotnet test` writes it;
    `lines` are (number, hits, "covered/total" or None)."""

    rows = "".join(
        f'<line number="{number}" hits="{hits}" branch="{"True" if cond else "False"}"'
        + (f' condition-coverage="50% ({cond})"' if cond else "")
        + " />"
        for number, hits, cond in lines
    )
    return (
        '\ufeff<?xml version="1.0" encoding="utf-8"?>\n<coverage><packages><package name="Demo">'
        f'<classes><class name="{name}" filename="{filename}"><methods/><lines>{rows}</lines>'
        "</class></classes></package></packages></coverage>"
    )


def write_report(root, project, text):
    write(root, f"reports/{project}/4f2c/me_host_2026.cobertura.xml", text)


def percent(start_line, end_line, path="src/Board.fs"):
    """The coverage `reports`, read inside the current directory, give a function of `path`."""

    scored = Function(name="choose", complexity=2, start_line=start_line, end_line=end_line, path=path)
    return BY_FILE_LINES.percent(load(["reports"], [], Path.cwd()).reports, scored)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_given_condition_coverage_when_scoring_then_it_wins_and_line_hits_score_a_branchless_function(project):
    source = project / "src" / "Board.fs"
    write_report(
        project,
        "Board.Tests",
        cobertura(source, [(3, 4, None), (4, 1, "1/2"), (5, 0, None), (8, 2, None), (9, 0, None)]),
    )
    assert percent(3, 5) == 50.0
    assert percent(8, 9) == 50.0


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_given_one_file_in_two_reports_when_loading_in_either_order_then_they_merge(project, order):
    reports = [[(3, 0, None), (4, 0, "0/2")], [(3, 35, None), (4, 2, "2/2")]]
    source = project / "src" / "Board.fs"
    write_report(project, "One.Tests", cobertura(source, reports[order[0]]))
    write_report(project, "Two.Tests", cobertura(source, reports[order[1]]))
    assert percent(3, 3) == 100.0
    assert percent(3, 4) == 100.0


def test_given_branches_on_a_line_in_two_reports_when_merging_then_the_highest_count_wins(project):
    source = project / "src" / "Board.fs"
    write_report(project, "One.Tests", cobertura(source, [(4, 1, "1/4")]))
    write_report(project, "Two.Tests", cobertura(source, [(4, 1, "3/4")]))
    assert percent(4, 4) == 75.0


def test_given_a_line_under_two_classes_when_reading_then_it_merges_like_two_reports(project):
    source = project / "src" / "Board.fs"
    first = cobertura(source, [(3, 0, "0/2")], name="Demo.Board")
    second = cobertura(source, [(3, 1, "1/2")], name="Demo.Board/choose@3")
    classes = first.split("<classes>")[1].split("</classes>")[0]
    write_report(project, "Board.Tests", second.replace("<classes>", "<classes>" + classes))
    assert percent(3, 3) == 50.0


def test_given_cobertura_and_lcov_for_one_file_when_scoring_then_cobertura_wins(project):
    source = project / "src" / "Board.fs"
    write(project, "reports/lcov.info", "SF:src/Board.fs\nDA:3,5\nend_of_record\n")
    write_report(project, "Board.Tests", cobertura(source, [(3, 0, None)]))
    assert percent(3, 3) == 0.0


def test_given_a_report_file_outside_the_project_when_matching_then_no_function_takes_it(project):
    outside = "/Users/runner/work/1/s/src/fsharp/src/FSharp.Core/array.fs"
    write_report(project, "Board.Tests", cobertura(outside, [(3, 5, None)]))
    assert percent(3, 3, path="array.fs") is None
    assert percent(3, 3, path="FSharp.Core/array.fs") is None


def test_given_a_windows_path_in_a_report_when_matching_then_no_function_takes_it(project):
    outside = "D:\\a\\_work\\1\\s\\src\\FSharp.Core\\array.fs"
    write_report(project, "Board.Tests", cobertura(outside, [(3, 5, None)]))
    assert percent(3, 3, path="src/FSharp.Core/array.fs") is None
    assert percent(3, 3, path="FSharp.Core/array.fs") is None


@pytest.mark.parametrize("broken", ["<coverage><packages>", cobertura("src/Board.fs", [("three", 1, None)])])
def test_given_an_unreadable_report_in_a_folder_when_loading_then_it_is_skipped_with_a_warning(project, capsys, broken):
    write_report(project, "Broken.Tests", broken)
    write_report(project, "Board.Tests", cobertura(project / "src" / "Board.fs", [(3, 1, None)]))
    assert percent(3, 3) == 100.0
    assert "unreadable Cobertura report" in capsys.readouterr().err


def test_given_a_script_no_report_mentions_when_running_then_its_function_scores_zero(project, capsys):
    write(project, "src/Board.fs", "module Board\n\nlet place x = x + 1\n")
    write(project, "build.fsx", "let publish target = target\n")
    write_report(project, "Board.Tests", cobertura((project / "src/Board.fs").resolve(), [(3, 1, None)]))

    assert run(["--coverage-report", "reports"]) == 0

    assert scores(capsys.readouterr().out) == {("place", 3): ("100.0%", "1.0"), ("publish", 1): ("0.0%", "2.0")}


def test_given_overlapping_report_paths_when_running_then_they_merge_and_each_file_is_read_once(project, capsys):
    write(project, "Demo/Board.fs", "module Demo.Board\n\nlet board x =\n    x + 1\n")
    write(project, "reports/a.xml", cobertura(project / "Demo/Board.fs", [(4, 1, None)]))
    write(project, "reports/b.xml", cobertura(project / "Demo/Board.fs", [(4, 0, None)]))
    write(project, "reports/z.info", "SF:Demo/Board.fs\nDA:4,0\nend_of_record\n")
    write(project, "reports/nested/half.xml", "<coverage><packages><pack")
    write(project, "reports/nested/other.info", "SF:Demo/Other.fs\nDA:1,1\nend_of_record\n")

    code = run(
        ["--coverage-report", "reports/a.xml", "--coverage-report", "reports", "--coverage-report", "reports/nested"]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert scores(captured.out) == {("board", 3): ("100.0%", "1.0")}
    assert captured.err.count("half.xml") == 1
    assert "dreck: reports/nested/half.xml: unreadable Cobertura report (" in captured.err


def test_given_a_damaged_cobertura_report_named_when_running_then_the_run_stops(project, capsys):
    write(project, "Demo/Board.fs", "module Demo.Board\n\nlet board x = x + 1\n")
    write(project, "reports/half.xml", "<coverage><packages><pack")

    assert run(["--coverage-report", "reports/half.xml"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("dreck: --coverage-report reports/half.xml: unreadable Cobertura report (")


def test_given_a_report_of_another_checkout_when_running_then_it_is_named_and_fsharp_hinted(project, capsys, monkeypatch):
    write(project, "project/Demo/Board.fs", "module Demo.Board\n\nlet board x = x + 1\n")
    write(project, "project/reports/other.xml", cobertura(project / "checkout/Demo/Board.fs", [(3, 1, None)]))
    monkeypatch.chdir(project / "project")
    assert run(["--coverage-report", "reports/other.xml"]) == 0

    captured = capsys.readouterr()
    assert scores(captured.out) == {("board", 3): ("-", "-")}
    assert captured.err.splitlines()[:-1] == [
        "dreck: --coverage-report reports/other.xml: matches none of the files being scored; "
        "was it made in another checkout or for another project?",
        "dreck: F#: coverage and CRAP show -; no coverage report given matches its files. "
        "Pass --coverage-report <the Cobertura reports of dotnet test>.",
    ]


def branch_lines(filename, condition):
    return (
        '<?xml version="1.0"?><coverage><packages><package name="Demo"><classes>'
        f'<class name="Demo" filename="{filename}"><methods/><lines>'
        f'<line number="3" hits="2" branch="True" {condition}/>'
        f'<line number="4" hits="1" branch="True" {condition}/>'
        '<line number="5" hits="0" branch="True" />'
        "</lines></class></classes></package></packages></coverage>"
    )


def test_given_branch_lines_without_condition_coverage_when_running_then_one_warning_is_printed(project, capsys):
    board = project / "Demo/Board.fs"
    write(project, "Demo/Board.fs", "module Demo.Board\n\nlet board x =\n    if x then 1\n    else 0\n")
    write(project, "merged/merged.xml", branch_lines(board, ""))
    write(project, "split/one.xml", branch_lines(board, 'condition-coverage="50% (1/2)"'))

    merged = run(["Demo", "--coverage-report", "merged", "--coverage-report", "merged/merged.xml"])
    merged_err = capsys.readouterr().err
    split = run(["Demo", "--coverage-report", "split"])
    split_err = capsys.readouterr().err

    assert merged == 0 and split == 0
    assert merged_err.count("VSTEST_DISABLE_ARTIFACTS_POSTPROCESSING=1") == 1
    assert merged_err.startswith(
        "dreck: merged/merged.xml: Cobertura report with branch lines that ran and carry no condition-coverage"
    )
    assert "VSTEST_DISABLE_ARTIFACTS_POSTPROCESSING" not in split_err


def test_given_reports_on_disk_when_running_without_a_report_path_then_none_is_read(project, capsys):
    board = project / "Demo/Board.fs"
    write(project, "Demo/Board.fs", "module Demo.Board\n\nlet board x = x + 1\n")
    write(project, "target/coverage/fsharp/Demo.Tests/r.cobertura.xml", cobertura(board, [(3, 1, None)]))

    assert run([]) == 0

    captured = capsys.readouterr()
    assert scores(captured.out) == {("board", 3): ("-", "-")}
    assert len(captured.err.splitlines()) == 1
