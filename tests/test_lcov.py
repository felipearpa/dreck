# Ported from crapper's tests/test_coverage.py and tests/test_edges.py: their LCOV, branch and report-path matching cases, the Go ones read as LCOV.
from dreck.cli import run
from dreck.coverage import BY_FILE_LINES, Reports, normalize_path, read_lcov, source_parts
from dreck.model import Function
from helpers import write


def function(path="Sources/Demo/Board.swift", start_line=3, end_line=5):
    return Function(name="choose", complexity=2, start_line=start_line, end_line=end_line, path=path)


def lcov(*records: tuple[str, str]) -> str:
    return "".join(f"SF:{path}\n{body}end_of_record\n" for path, body in records)


def percent(text: str, scored: Function, sources: list[str] | None = None) -> float | None:
    reports = Reports(lines=read_lcov(text), sources=source_parts(sources or []))
    return BY_FILE_LINES.percent(reports, scored)


def test_given_line_hits_when_scoring_then_the_functions_lines_count_and_a_missing_file_gives_nothing():
    text = lcov(("Sources/Demo/Board.swift", "DA:3,1\nDA:4,0\nDA:9,3\n"))
    assert percent(text, function(start_line=3, end_line=5)) == 50.0
    assert percent(text, function(path="Sources/Demo/Missing.swift")) is None
    assert percent(text, function(start_line=6, end_line=8)) == 0.0


def test_given_branch_records_when_scoring_then_they_win_over_line_hits():
    text = lcov(("Sources/Demo/Board.swift", "DA:2,1\nDA:3,1\nBRDA:3,0,0,1\nBRDA:3,0,1,-\n"))
    parsed = read_lcov(text)["Sources/Demo/Board.swift"]
    assert parsed[2] == (1, 1)
    assert parsed.branches[3] == (1, 2)
    assert percent(text, function(start_line=2, end_line=3)) == 50.0


def test_given_a_branchless_span_when_scoring_then_line_coverage_is_kept():
    text = lcov(("Sources/Demo/Board.swift", "DA:2,1\nDA:3,0\nBRDA:8,0,0,1\nBRDA:8,0,1,0\n"))
    assert percent(text, function(start_line=2, end_line=3)) == 50.0


def test_given_a_record_without_end_when_reading_lcov_then_the_file_is_kept():
    parsed = read_lcov("SF:a.swift\nDA:1,1\nSF:b.swift\nDA:2,0\n")
    assert parsed["a.swift"][1] == (1, 1)
    assert parsed["b.swift"][2] == (0, 1)


def test_when_normalizing_a_path_then_url_and_dot_prefixes_are_stripped():
    assert normalize_path("file:./src//demo/core.swift") == "src/demo/core.swift"
    assert normalize_path("%2E%2Fsrc%2Fcore.swift") == "src/core.swift"


def test_given_report_paths_with_prefixes_when_matching_then_the_closest_wins_and_a_tie_matches_nothing():
    specific = lcov(("other/proj/src/a.swift", "DA:1,0\n"), ("proj/src/a.swift", "DA:1,1\n"))
    assert percent(specific, function(path="src/a.swift", start_line=1, end_line=2)) == 100.0
    tied = lcov(("proj/a.swift", "DA:1,1\n"), ("other/a.swift", "DA:1,0\n"))
    assert percent(tied, function(path="a.swift", start_line=1, end_line=2)) is None
    assert percent(specific, function(path="/", start_line=1, end_line=2)) is None


def test_given_an_exact_key_and_a_suffix_when_matching_then_the_exact_key_wins():
    text = lcov(("a/b/main.swift", "DA:1,1\n"), ("b/main.swift", "DA:1,0\n"))
    assert percent(text, function(path="b/main.swift", start_line=1, end_line=2)) == 0.0
    assert percent(text, function(path="a/b/main.swift", start_line=1, end_line=2)) == 100.0


def test_given_a_shorter_and_a_longer_source_when_matching_then_the_shorter_takes_nothing():
    text = lcov(("a/b/main.swift", "DA:1,1\n"))
    sources = ["b/main.swift", "a/b/main.swift"]
    assert percent(text, function(path="b/main.swift", start_line=1, end_line=2), sources) is None
    assert percent(text, function(path="a/b/main.swift", start_line=1, end_line=2), sources) == 100.0


def test_given_a_short_report_key_when_matching_then_it_matches_only_a_lone_longer_source():
    text = lcov(("board.swift", "DA:4,1\n"))
    scored = function(path="cmd/board.swift", start_line=4, end_line=6)
    assert percent(text, scored, ["cmd/board.swift"]) == 100.0
    assert percent(text, scored, ["cmd/board.swift", "other/board.swift"]) is None
    assert percent(text, function(path="other/board.swift"), ["cmd/board.swift", "other/board.swift"]) is None


def test_given_a_report_keyed_by_a_longer_path_when_matching_then_it_is_found():
    text = lcov(("proj/src/demo/core.swift", "DA:3,1\nDA:4,0\n"))
    assert percent(text, function(path="src/demo/core.swift", start_line=3, end_line=4)) == 50.0


BOARD = "func place(_ x: Int) -> Int {\n    return x\n}\n"


def test_given_an_lcov_file_of_any_name_when_running_then_it_is_read_and_a_short_path_takes_nothing(
    tmp_path, capsys, monkeypatch
):
    write(tmp_path, "b/main.swift", BOARD)
    write(tmp_path, "a/b/main.swift", BOARD)
    write(tmp_path, "reports/any-name.data", lcov(("a/b/main.swift", "DA:1,1\nDA:2,1\nDA:3,1\n")))
    monkeypatch.chdir(tmp_path)

    assert run(["a", "b", "--coverage-report", "reports"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "crap 2.0  cc 1  cov 0.0%  b/main.swift:1-3  place",
        "crap 1.0  cc 1  cov 100.0%  a/b/main.swift:1-3  place",
    ]
