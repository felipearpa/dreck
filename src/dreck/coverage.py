# Adapted from crapper's src/crapper/coverage.py (0BSD): its format detection, its Cobertura, JaCoCo and LCOV readers, its report-path matching, and its lookups by JVM class and by file and line range.
"""Read the coverage reports given by path, and find a function in them.

A report is told by its content, not its name. A language spec names the
`Lookup` that finds its functions in the reports.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from dreck import llvm
from dreck.model import Function
from dreck.paths import display_path


class ReportError(Exception):
    """A given report path that does not exist, holds no report, names a damaged one,
    or is Xcode derived data that cannot be converted."""


class Lines(dict):
    """One file's lines, `line → (covered, total)`, and its branches, `line → (covered, total)`.

    Each `BRDA` record on a line counts as one branch.
    """

    def __init__(self):
        super().__init__()
        self.branches: dict[int, tuple[int, int]] = {}


@dataclass
class Reports:
    """`methods` maps a JVM class (`pkg.Outer$Inner`) to its methods' instruction
    counts, as (method name, missed, covered). `lines` holds each LCOV record
    by the path it names; `counts` each line's hits, by absolute path, from
    LLVM's coverage tools; `cobertura` each Cobertura file by its path relative
    to the current directory. `sources` are the selected files' paths, split
    into folders, so a short path cannot take a longer file's record.
    """

    methods: dict[str, list[tuple[str, int, int]]] = field(default_factory=dict)
    lines: dict[str, Lines] = field(default_factory=dict)
    counts: dict[str, dict[int, int]] = field(default_factory=dict)
    cobertura: dict[str, Lines] = field(default_factory=dict)
    sources: list[tuple[str, ...]] = field(default_factory=list)
    _keys: dict[str, str | None] = field(default_factory=dict, repr=False, compare=False)

    def add(self, other: Reports) -> None:
        """Methods add up; the last LCOV record of a file wins; LLVM counts and Cobertura lines merge line by line."""

        for name, methods in other.methods.items():
            self.methods.setdefault(name, []).extend(methods)
        self.lines.update(other.lines)
        for path, counts in other.counts.items():
            into = self.counts.setdefault(path, {})
            for number, hits in counts.items():
                into[number] = into.get(number, 0) + hits
        for path, record in other.cobertura.items():
            into = self.cobertura.setdefault(path, Lines())
            for number, (covered, _total) in record.items():
                _merge_line(into, number, covered, record.branches.get(number))

    @cached_property
    def files(self) -> dict[str, Lines]:
        """Every file's lines, read once every report is added.

        LLVM counts, keyed by absolute path, replace an LCOV record keyed by
        that same path, and a Cobertura record replaces either keyed by its
        path; a record keyed otherwise stays beside them.
        """

        found = dict(self.lines)
        for path in sorted(self.counts):
            record = Lines()
            for number in sorted(self.counts[path]):
                record[number] = (1 if self.counts[path][number] > 0 else 0, 1)
            found[path] = record
        found.update(self.cobertura)
        return found

    def record(self, path: str) -> Lines | None:
        """The lines of the source file at `path`, as the report prints it."""

        if path not in self._keys:
            self._keys[path] = _select_key(list(self.files), path, self.sources) if self.files else None
        key = self._keys[path]
        return None if key is None else self.files[key]


@dataclass(frozen=True)
class Lookup:
    """How a language's functions are found in the reports.

    `holds` says whether the reports know the function's file or class, which
    makes its language one the reports cover; `percent` is None when they
    hold nothing for the function itself.
    """

    holds: Callable[[Reports, Function], bool]
    percent: Callable[[Reports, Function], float | None]


def _percent(covered: int, total: int) -> float:
    return 100.0 * covered / total if total > 0 else 0.0


def _jvm_percent(reports: Reports, function: Function) -> float | None:
    """Sum the methods one function compiles into.

    `name-<hash>` is a value-class mangling; `name$<anything>` is a lambda, an
    `internal` module suffix, `$suspendImpl`, or a default-argument bridge.
    Kover writes no line numbers, so overloads share one percentage.
    """

    name = function.name
    found = [
        (missed, covered)
        for method, missed, covered in reports.methods.get(function.jvm_class, [])
        if method == name or method.startswith((f"{name}-", f"{name}$"))
    ]
    if not found:
        return None
    covered = sum(covered for _missed, covered in found)
    return _percent(covered, covered + sum(missed for missed, _covered in found))


BY_JVM_CLASS = Lookup(
    holds=lambda reports, function: function.jvm_class in reports.methods,
    percent=_jvm_percent,
)


def normalize_path(path: str) -> str:
    text = unquote(path).replace("\\", "/")
    if text.startswith("file:"):
        text = text[5:]
    while text.startswith("./"):
        text = text[2:]
    while "//" in text:
        text = text.replace("//", "/")
    return text


def _segments(path: str) -> list[str]:
    return [part for part in normalize_path(path).split("/") if part]


def _candidates(path: str) -> list[str]:
    """The ways a report may spell a source file: as given, absolute, and each without `src/`."""

    relative = normalize_path(path)
    absolute = normalize_path(str(Path(path).resolve())) if path else relative
    found: list[str] = []
    for value in (relative, absolute, re.sub(r"^src/", "", relative), re.sub(r"/src/", "/", absolute)):
        if value and value not in found:
            found.append(value)
    return found


def source_parts(paths: list[str]) -> list[tuple[str, ...]]:
    """Each spelling of each selected file, split into folders, once."""

    found: dict[tuple[str, ...], None] = {}
    for path in paths:
        for candidate in _candidates(path):
            parts = tuple(_segments(candidate))
            if parts:
                found.setdefault(parts)
    return list(found)


def _ends_with(parts: list[str], suffix: list[str] | tuple[str, ...]) -> bool:
    return len(suffix) <= len(parts) and parts[len(parts) - len(suffix) :] == list(suffix)


def _longer_source_owns(key: list[str], length: int, sources: list[tuple[str, ...]]) -> bool:
    return any(len(other) > length and _ends_with(key, other) for other in sources)


def _another_source_ends_with(key: list[str], sources: list[tuple[str, ...]], own: set[tuple[str, ...]]) -> bool:
    return any(other not in own and len(other) >= len(key) and _ends_with(list(other), key) for other in sources)


def _forward(keys: list[tuple[str, str]], spellings: list[list[str]], sources: list[tuple[str, ...]]) -> list[str]:
    """Keys that are a spelling plus a prefix, fewest extra folders first."""

    found: list[tuple[int, str]] = []
    for parts in spellings:
        for key, normal in keys:
            key_parts = _segments(normal)
            if _ends_with(key_parts, parts) and not _longer_source_owns(key_parts, len(parts), sources):
                found.append((len(key_parts) - len(parts), key))
    if not found:
        return []
    fewest = min(extra for extra, _key in found)
    return list(dict.fromkeys(key for extra, key in found if extra == fewest))


def _reverse(keys: list[tuple[str, str]], spellings: list[list[str]], sources: list[tuple[str, ...]]) -> str | None:
    """The one key that is a shorter tail of a spelling, and of no other source."""

    own = {tuple(parts) for parts in spellings}
    found: list[str] = []
    for parts in spellings:
        for key, normal in keys:
            key_parts = _segments(normal)
            if not key_parts or len(key_parts) >= len(parts) or not _ends_with(parts, key_parts):
                continue
            if not _another_source_ends_with(key_parts, sources, own):
                found.append(key)
    unique = list(dict.fromkeys(found))
    return unique[0] if len(unique) == 1 else None


def _select_key(keys: list[str], path: str, sources: list[tuple[str, ...]]) -> str | None:
    """The report key for one source file.

    An exact path wins. A report path may be the source path plus a prefix
    (`proj/src/a` for `src/a`), the fewest extra folders winning and a tie
    matching nothing. It is not a match when another source file is a longer
    suffix of that key, so `b/main` does not take `a/b/main`. Failing both,
    a key that is a shorter tail of the path matches when no other source
    ends with it.
    """

    normals = [(key, normalize_path(key)) for key in keys]
    candidates = _candidates(path)
    for candidate in candidates:
        for key, normal in normals:
            if normal == candidate:
                return key
    spellings = [parts for parts in (_segments(candidate) for candidate in candidates) if parts]
    forward = _forward(normals, spellings, sources)
    if forward:
        return forward[0] if len(forward) == 1 else None
    return _reverse(normals, spellings, sources)


def _sum(found: dict[int, tuple[int, int]], start: int, end: int) -> tuple[int, int]:
    covered = total = 0
    for number in range(start, end + 1):
        entry = found.get(number)
        if entry is not None:
            covered += entry[0]
            total += entry[1]
    return covered, total


def _lines_percent(reports: Reports, function: Function) -> float | None:
    """Branch coverage of the function's lines when they hold a branch record, line coverage otherwise."""

    record = reports.record(function.path)
    if record is None:
        return None
    covered, total = _sum(record.branches, function.start_line, function.end_line)
    if total:
        return _percent(covered, total)
    return _percent(*_sum(record, function.start_line, function.end_line))


BY_FILE_LINES = Lookup(
    holds=lambda reports, function: reports.record(function.path) is not None,
    percent=_lines_percent,
)


_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)


def _counter(method) -> tuple[int, int] | None:
    for child in method:
        if child.tag == "counter" and child.get("type") == "INSTRUCTION":
            return int(child.get("missed") or "0"), int(child.get("covered") or "0")
    return None


def read_jacoco(text: str) -> Reports:
    """JaCoCo's XML, and Kover's, which has its shape without line numbers."""

    reports = Reports()
    for class_node in ET.fromstring(_DOCTYPE.sub("", text)).iter("class"):
        name = class_node.get("name", "").replace("/", ".")
        for method in class_node:
            counts = _counter(method) if method.tag == "method" else None
            if counts is not None:
                reports.methods.setdefault(name, []).append((method.get("name", ""), *counts))
    return reports


_DA = re.compile(r"DA:(\d+),(\d+)")
_BRDA = re.compile(r"BRDA:(\d+),([^,]*),([^,]*),(-|\d+)")


def _taken(hits: str) -> bool:
    return hits.isdigit() and int(hits) > 0


def read_lcov(text: str) -> dict[str, Lines]:
    """Each `SF:` record's lines and branches, keyed by the path it names; a record lacking `end_of_record` is kept."""

    found: dict[str, Lines] = {}
    current: Lines | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            current = found[line[3:]] = Lines()
        elif line == "end_of_record":
            current = None
        elif current is not None and (hit := _DA.match(line)):
            current[int(hit[1])] = (1 if int(hit[2]) > 0 else 0, 1)
        elif current is not None and (branch := _BRDA.match(line)):
            covered, total = current.branches.get(int(branch[1]), (0, 0))
            current.branches[int(branch[1])] = (covered + _taken(branch[4]), total + 1)
    return found


_CONDITIONS = re.compile(r"\((\d+)/(\d+)\)")


def _cobertura_key(filename: str, root: Path) -> str | None:
    """Report path relative to `root`, so every report spells one file alike.

    An absolute path outside the project, such as a framework library's
    build paths, is dropped, and so is a Windows path with a drive. A
    relative path is kept as written.
    """

    if PureWindowsPath(filename).drive:
        return None
    path = Path(normalize_path(filename))
    if not path.is_absolute():
        return path.as_posix()
    for candidate in (path, path.resolve()):
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            continue
    return None


def _condition_coverage(line) -> tuple[int, int] | None:
    if line.get("branch", "").lower() != "true":
        return None
    found = _CONDITIONS.search(line.get("condition-coverage") or "")
    if found is None:
        return None
    return int(found.group(1)), int(found.group(2))


def _merge_line(record: Lines, number: int, covered: int, branch: tuple[int, int] | None) -> None:
    """A line is covered when any report covered it; its branches keep the best counts."""

    record[number] = (max(record.get(number, (0, 1))[0], covered), 1)
    if branch is None:
        return
    current = record.branches.get(number, (0, 0))
    record.branches[number] = (max(current[0], branch[0]), max(current[1], branch[1]))


def read_cobertura(text: str, root: Path) -> tuple[dict[str, Lines], bool]:
    """Files keyed by their path relative to `root`, classes that name one file
    merged, and whether a branch line that ran has no `condition-coverage`.

    A solution-wide `dotnet test` merges its test projects' reports and drops
    that value on lines more than one project reached.
    """

    found: dict[str, Lines] = {}
    lacking = False
    for class_node in ET.fromstring(text.lstrip("\ufeff")).iter("class"):
        key = _cobertura_key(class_node.get("filename", ""), root)
        if key is None:
            continue
        record = found.setdefault(key, Lines())
        for line in class_node.iter("line"):
            number = int(line.get("number") or "0")
            covered = 1 if int(line.get("hits") or "0") > 0 else 0
            branch = _condition_coverage(line)
            if branch is None and covered and line.get("branch", "").lower() == "true":
                lacking = True
            _merge_line(record, number, covered, branch)
    return found, lacking


def _cobertura(text: str, path: Path, root: Path) -> Reports:
    found, lacking = read_cobertura(text, root.resolve())
    if lacking:
        print(
            f"dreck: {path}: Cobertura report with branch lines that ran and carry no condition-coverage, "
            "as a solution-wide dotnet test leaves when it merges its test projects' reports; "
            "their functions may score wrongly. Run dotnet test with "
            "VSTEST_DISABLE_ARTIFACTS_POSTPROCESSING=1 to keep one report per test project.",
            file=sys.stderr,
        )
    return Reports(cobertura=found)


_XML_PROLOG = re.compile(r"\s*(?:<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^>]*>|\s)*<([\w.:-]+)", re.DOTALL)
_LCOV_SOURCE = re.compile(r"^\s*SF:", re.MULTILINE)
_EXPORT = re.compile(r'"type"\s*:\s*"llvm\.coverage\.json\.export"')
_EXPORT_HEAD = re.compile(r'\s*\{\s*"data"\s*:\s*\[\s*\{\s*"files"\s*:\s*\[')
_HEAD_BYTES = 4096
# Each reader takes a report's text, its path, the selected files, and the folder dreck runs in.
Reader = Callable[[str, Path, list[Path], Path], Reports]
# Each format: its name in messages and its reader.
_FORMATS: dict[str, tuple[str, Reader]] = {
    "cobertura": ("Cobertura", lambda text, path, _files, root: _cobertura(text, path, root)),
    "jacoco": ("JaCoCo or Kover", lambda text, _path, _files, _root: read_jacoco(text)),
    "lcov": ("LCOV", lambda text, _path, _files, _root: Reports(lines=read_lcov(text))),
    "export": ("llvm-cov JSON export", lambda text, _path, files, _root: Reports(counts=llvm.read_export(text, files))),
}
_XML_ROOTS = {"coverage": "cobertura", "report": "jacoco"}
_KNOWN = "Xcode derived data, Cobertura, JaCoCo or Kover XML, LCOV, llvm-cov JSON export"


def _tail(path: Path) -> str:
    """The last bytes of a file: an llvm-cov JSON export names its type at its end."""

    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - _HEAD_BYTES))
        return handle.read().decode("utf-8", errors="replace")


def _format(path: Path) -> tuple[str, Reader] | None:
    """The format of a file, told from its first bytes, or a JSON file's last, not its name."""

    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            head = handle.read(_HEAD_BYTES).lstrip("﻿")
        tail = _tail(path) if head.lstrip().startswith("{") else ""
    except OSError:
        return None
    root = _XML_PROLOG.match(head)
    if root is not None:
        found = _XML_ROOTS.get(root.group(1))
        return None if found is None else _FORMATS[found]
    if _LCOV_SOURCE.search(head):
        return _FORMATS["lcov"]
    if _EXPORT_HEAD.match(head) or (tail and _EXPORT.search(head + tail)):
        return _FORMATS["export"]
    return None


def _files_in(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(found for found in path.rglob("*") if found.is_file())
    return [path]


def _read_derived_data(path: Path, read: dict[Path, Reports | str], files: list[Path]) -> list[Path]:
    """Convert Xcode derived data without searching it: its package checkouts hold report-like fixtures."""

    real = path.resolve()
    if real not in read:
        try:
            read[real] = Reports(counts=llvm.read_derived_data(path, files))
        except llvm.ConversionError as exc:
            raise ReportError(f"dreck: --coverage-report {path}: cannot convert Xcode derived data: {exc}.") from exc
    return [real]


def _read_path(path: Path, read: dict[Path, Reports | str], files: list[Path], root: Path) -> list[Path]:
    """Read the reports at one given path into `read`, keyed by real path, each once.

    A damaged report is kept as its message. Named directly it stops the run,
    also when a folder reached it first; inside a folder it is skipped with a
    warning. Returns the real paths of the reports it holds that could be read.
    """

    if llvm.is_derived_data(path):
        return _read_derived_data(path, read, files)
    reached: list[Path] = []
    for file in _files_in(path):
        real = file.resolve()
        if real not in read:
            found = _format(file)
            if found is None:
                continue
            label, reader = found
            try:
                read[real] = reader(file.read_text(encoding="utf-8", errors="replace"), file, files, root)
            except (ET.ParseError, OSError, ValueError) as exc:
                read[real] = f"{file}: unreadable {label} report ({exc})"
                if file != path:
                    print(f"dreck: {read[real]}; skipped.", file=sys.stderr)
        if isinstance(read[real], str) and file == path:
            raise ReportError(f"dreck: --coverage-report {read[real]}.")
        if not isinstance(read[real], str):
            reached.append(real)
    return reached


@dataclass
class Coverage:
    """Every given report combined, and each given path with its own reports."""

    reports: Reports
    given: list[tuple[str, Reports]]


def load(paths: list[str], files: list[Path], root: Path) -> Coverage:
    """The reports at the given paths, a relative one read inside the current directory,
    for the selected `files`.

    Methods reported under one class add up, whichever reports hold them;
    LLVM line counts add up line by line, whatever the order of the paths;
    Cobertura lines merge, a line covered when any report covered it;
    the last LCOV record of a file wins, and LLVM counts, keyed by absolute
    path, replace an LCOV record keyed by that same path; a Cobertura record,
    keyed by its path relative to `root`, the folder dreck runs in, replaces either
    keyed by that same path. A file reached
    twice is read once. Only the selected files are kept from
    derived data and llvm-cov exports.
    """

    read: dict[Path, Reports | str] = {}
    reached: list[tuple[str, list[Path]]] = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise ReportError(f"dreck: --coverage-report {raw}: no such file or folder.")
        found = _read_path(path, read, files, root)
        if not found:
            raise ReportError(f"dreck: --coverage-report {raw}: holds no coverage report dreck reads ({_KNOWN}).")
        reached.append((raw, found))
    sources = source_parts([display_path(file, root) for file in files])
    combined = Reports(sources=sources)
    for report in read.values():
        if isinstance(report, Reports):
            combined.add(report)
    given = []
    for raw, found in reached:
        own = Reports(sources=sources)
        for real in found:
            own.add(read[real])
        given.append((raw, own))
    return Coverage(combined, given)
