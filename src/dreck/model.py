# Adapted from crapper's src/crapper/model.py (0BSD).
from dataclasses import dataclass


@dataclass(frozen=True)
class Function:
    """`path` is the file as the report prints it. `jvm_class` is the class a JVM
    coverage report files the function under, for the languages that compile
    to one; None otherwise.
    """

    name: str
    complexity: int
    start_line: int
    end_line: int
    path: str
    jvm_class: str | None = None


@dataclass(frozen=True)
class Entry:
    """`coverage` (0 to 100) and `crap` are None when not measured."""

    name: str
    complexity: int
    coverage: float | None
    crap: float | None
    path: str
    start_line: int
    end_line: int
