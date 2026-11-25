"""The text report: one labelled line per function."""

from dreck.model import Entry


def _line(entry: Entry) -> str:
    crap = "-" if entry.crap is None else f"{entry.crap:.1f}"
    coverage = "-" if entry.coverage is None else f"{entry.coverage:.1f}%"
    # The name comes last: some languages allow spaces in it.
    return (
        f"crap {crap}  cc {entry.complexity}  cov {coverage}  "
        f"{entry.path}:{entry.start_line}-{entry.end_line}  {entry.name}"
    )


def render(entries: list[Entry]) -> str:
    return "".join(f"{_line(entry)}\n" for entry in entries)
