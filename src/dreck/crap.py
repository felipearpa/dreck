# Adapted from crapper's src/crapper/crap.py (0BSD), with the coverage rule of its src/crapper/analyze.py.
"""The CRAP formula, its rounding, the coverage rule, and the report order."""

from pathlib import Path

from dreck.coverage import Coverage
from dreck.discover import spec_of
from dreck.model import Entry, Function
from dreck.spec import LanguageSpec


def crap_score(complexity: int, coverage: float | None) -> float | None:
    """CRAP = CC² × (1 − coverage)³ + CC.

    `coverage` is a percentage from 0 to 100. Missing coverage yields no
    score, which the report shows as `-`.
    """

    if coverage is None:
        return None
    cc = float(complexity)
    uncovered = 1.0 - (float(coverage) / 100.0)
    return (cc * cc * uncovered * uncovered * uncovered) + cc


def _rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def entry_of(function: Function, coverage: float | None) -> Entry:
    coverage = _rounded(coverage)
    return Entry(
        name=function.name,
        complexity=function.complexity,
        coverage=coverage,
        crap=_rounded(crap_score(function.complexity, coverage)),
        path=function.path,
        start_line=function.start_line,
        end_line=function.end_line,
    )


def _specs(functions: list[Function]) -> dict[Function, LanguageSpec]:
    return {function: spec_of(Path(function.path)) for function in functions}


def scored(functions: list[Function], coverage: Coverage | None) -> tuple[list[Entry], list[LanguageSpec]]:
    """Each function's entry, and the languages of `functions` no given report covers.

    Without reports, coverage is not measured. With reports, a language is
    covered once they hold one of its functions' files or classes; a function
    of it they leave out then scores 0%, so it sorts with the other scores
    instead of sinking among the unmeasured. A language they do not cover is
    not measured.
    """

    if coverage is None:
        return [entry_of(function, None) for function in functions], []
    spec = _specs(functions)
    covered = {spec[function] for function in functions if spec[function].lookup.holds(coverage.reports, function)}
    entries = []
    for function in functions:
        percent = None
        if spec[function] in covered:
            percent = spec[function].lookup.percent(coverage.reports, function)
            percent = 0.0 if percent is None else percent
        entries.append(entry_of(function, percent))
    missed = sorted(set(spec.values()) - covered, key=lambda found: found.name)
    return entries, missed


def unmatched(functions: list[Function], coverage: Coverage) -> list[str]:
    """The given report paths that hold none of `functions`."""

    spec = _specs(functions)
    return [
        path
        for path, reports in coverage.given
        if functions and not any(spec[function].lookup.holds(reports, function) for function in functions)
    ]


def worst_first(entries: list[Entry]) -> list[Entry]:
    """Worst CRAP first; unscored rows follow, most complex first; ties by path, then line."""

    def key(entry: Entry) -> tuple:
        if entry.crap is None:
            return (1, -entry.complexity, entry.path, entry.start_line)
        return (0, -entry.crap, entry.path, entry.start_line)

    return sorted(entries, key=key)
