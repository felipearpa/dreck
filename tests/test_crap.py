# Ported from crapper's tests/test_crap.py: the formula, its rounding and the order.
from dreck.crap import crap_score, entry_of, worst_first
from dreck.model import Entry, Function
from dreck.report import render


def entry(**kwargs):
    defaults = dict(
        name="total",
        complexity=1,
        coverage=100.0,
        crap=1.0,
        path="src/Demo.kt",
        start_line=1,
        end_line=2,
    )
    defaults.update(kwargs)
    return Entry(**defaults)


def test_when_computing_crap_then_the_formula_matches_crap4clj():
    assert crap_score(5, 100.0) == 5.0
    assert crap_score(5, 0.0) == 30.0
    assert crap_score(1, 100.0) == 1.0
    assert abs(crap_score(8, 45.0) - 18.648) < 0.01
    assert crap_score(3, None) is None


def test_when_scoring_then_coverage_and_crap_are_rounded_to_four_decimals():
    function = Function(name="run", complexity=8, start_line=3, end_line=9, path="A.kt")
    scored = entry_of(function, 45.123456)
    assert scored.coverage == 45.1235
    assert scored.crap == round(crap_score(8, 45.1235), 4)
    assert entry_of(function, None) == Entry("run", 8, None, None, "A.kt", 3, 9)


def test_given_scored_and_unscored_rows_when_sorting_then_unscored_follow():
    rows = worst_first(
        [
            entry(name="missing", crap=None, coverage=None),
            entry(name="mid", crap=5.0),
            entry(name="worst", crap=30.0),
        ]
    )
    assert [row.name for row in rows] == ["worst", "mid", "missing"]


def test_given_a_low_score_and_an_unscored_row_when_sorting_then_the_score_comes_first():
    rows = worst_first(
        [
            entry(name="plain", crap=1.0, complexity=1),
            entry(name="large", crap=None, coverage=None, complexity=8),
        ]
    )
    assert [row.name for row in rows] == ["plain", "large"]


def test_given_unscored_rows_when_sorting_then_the_most_complex_comes_first():
    rows = worst_first(
        [
            entry(name="small", crap=None, coverage=None, complexity=1),
            entry(name="large", crap=None, coverage=None, complexity=8),
        ]
    )
    assert [row.name for row in rows] == ["large", "small"]


def test_given_equal_rows_when_sorting_then_path_then_line_decide():
    for crap in (4.0, None):
        rows = worst_first(
            [
                entry(name="b20", path="b.kt", start_line=20, crap=crap, complexity=4),
                entry(name="a9", path="a.kt", start_line=9, crap=crap, complexity=4),
                entry(name="b3", path="b.kt", start_line=3, crap=crap, complexity=4),
            ]
        )
        assert [row.name for row in rows] == ["a9", "b3", "b20"]


def test_when_rendering_then_each_line_labels_its_numbers_then_location_and_name():
    text = render(
        [
            entry(name="signIn", complexity=7, coverage=0.0, crap=56.0, path="app/Login.kt", start_line=42, end_line=88),
            entry(name="body", complexity=4, coverage=35.0, crap=8.4375, path="Login.swift", start_line=10, end_line=31),
            entry(name="handle | other", complexity=11, coverage=None, crap=None, path="Handler.fs", start_line=5, end_line=60),
        ]
    )
    assert text == (
        "crap 56.0  cc 7  cov 0.0%  app/Login.kt:42-88  signIn\n"
        "crap 8.4  cc 4  cov 35.0%  Login.swift:10-31  body\n"
        "crap -  cc 11  cov -  Handler.fs:5-60  handle | other\n"
    )
