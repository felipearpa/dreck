# Adapted from doppel's src/doppel/cli.py, adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/cli.py (0BSD).
"""Command line: `dreck [options] [path-or-fragment ...]` prints one labelled line per function, worst first."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dreck.changed import ChangedLines, GitStatusError, changed_files, changed_lines
from dreck.coverage import ReportError, load
from dreck.crap import scored, unmatched, worst_first
from dreck.discover import source_files, spec_of, specs
from dreck.model import Entry
from dreck.report import render
from dreck.paths import display_path
from dreck.scan import read_files

HELP = """\
Usage: dreck [options] [path-or-fragment ...]

Score the complexity, coverage and CRAP of each function, worst first, one
line per function:

  crap 56.0  cc 7  cov 0.0%  app/auth/Login.src:42-88  signIn

CRAP = CC² × (1 − coverage)³ + CC. CRAP and coverage print - when coverage
was not measured; those functions follow the scored ones, most complex
first, then by path and line. The location is file:start-end, relative to
the current directory, and the name, the function's own without its class,
comes last. dreck starts no test run and writes no file.

Languages: {languages}.

Options:
  -h, --help                Print this help and exit.
  --changed                 Score only the files git reports as added,
                            modified or untracked, among those the paths,
                            fragments and skips select.
  --changed-functions       Score only the functions holding a line
                            changed since the last commit (git diff
                            HEAD), and every function of an untracked
                            file, among the files the paths, fragments
                            and skips select.
  --coverage-report <path>  Read coverage from this report file, or from
                            every report in this folder. May be repeated.
                            Reports are told by content, not name:
                              XML whose root is coverage: Cobertura
                              XML whose root is report: JaCoCo or Kover
                              text with SF: records: LCOV
                              JSON of type llvm.coverage.json.export:
                                an llvm-cov export
                              a folder holding Build/ProfileData, or one
                                folder above it: Xcode derived data, read
                                with xcrun llvm-cov and not searched
                            In a folder, other files are skipped quietly,
                            and a damaged report is skipped with a warning.
                            Methods of one class add up across reports,
                            and so do the line counts of derived data and
                            llvm-cov exports; Cobertura lines merge, and a
                            Cobertura record of a file beats an LCOV one.
                            Once a report holds one of a language's
                            classes or files, a function of it the reports
                            leave out scores 0%. A language none of whose
                            classes or files is in a given report prints -
                            for coverage and CRAP, with one hint on
                            standard error naming the reports to pass for
                            it. A given path that holds none of the
                            functions scored is named in a warning.

Arguments:
  path            File or folder to score instead of the current directory.
                  Test code is scored when its path is named. With
                  --changed or --changed-functions, git is asked in each
                  named folder, or a named file's folder, so a path in
                  another repository reads that repository's changes.
  fragment        Any other argument: only files whose path, as the report
                  prints it, contains it are scored.

Exit codes:
  0  the run finished
  1  usage error; git failing for --changed or --changed-functions
     (outside a git repository, for one); or, with a file to score, a
     --coverage-report path that does not exist, holds no report, names a
     report that cannot be read, or is Xcode derived data that cannot be
     converted
"""


def help_text() -> str:
    languages = ", ".join(
        f"{spec.name} ({' '.join(sorted(spec.extensions))})" for spec in specs()
    )
    return HELP.format(languages=languages)


@dataclass
class Options:
    positionals: list[str] = field(default_factory=list)
    reports: list[str] = field(default_factory=list)
    help: bool = False
    changed: bool = False
    changed_functions: bool = False


def parse_args(args: list[str]) -> Options:
    """Raises ValueError naming what is wrong."""

    if any(arg in {"-h", "--help"} for arg in args):
        return Options(help=True)
    options = Options()
    rest = iter(args)
    for arg in rest:
        if arg == "--coverage-report":
            path = next(rest, None)
            if path is None:
                raise ValueError("--coverage-report needs a path")
            options.reports.append(path)
        elif arg == "--changed":
            options.changed = True
        elif arg == "--changed-functions":
            options.changed_functions = True
        elif arg.startswith("-"):
            raise ValueError(f"Unknown option: {arg}")
        else:
            options.positionals.append(arg)
    return options


def _split(root: Path, args: list[str]) -> tuple[list[Path], list[str]]:
    """Arguments naming an existing path, and the rest, which are fragments."""

    existing: list[Path] = []
    fragments: list[str] = []
    for arg in args:
        path = Path(arg)
        if not path.is_absolute():
            path = root / arg
        if path.exists():
            existing.append(path.resolve())
        else:
            fragments.append(arg)
    return existing, fragments


def _files_under(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(source_files(path))
        elif spec_of(path) is not None:
            files.append(path)
    return files


def select(root: Path, existing: list[Path], fragments: list[str]) -> list[Path]:
    """Files under the `existing` paths, or under `root` when none is named.

    A fragment keeps only the files whose displayed path contains it.
    """

    files = _files_under(existing) if existing else source_files(root)
    if fragments:
        files = [
            path for path in files if any(fragment in display_path(path, root) for fragment in fragments)
        ]
    return sorted(set(files), key=lambda path: path.as_posix())


class _Stop(Exception):
    """A reason dreck exits 1, printed on standard error."""


def _git_folders(root: Path, searched: list[Path]) -> set[Path]:
    """Where git is asked: in each named folder, or a named file's folder, or
    in `root` when no path is named."""

    return {path if path.is_dir() else path.parent for path in searched} or {root}


def _changed_lines(root: Path, searched: list[Path]) -> ChangedLines:
    """The changed lines of every repository holding a git folder.

    Folders in one repository give the same answer, so a later one only adds
    files from another repository.
    """

    changes: ChangedLines = {}
    for folder in _git_folders(root, searched):
        for path, lines in changed_lines(folder).items():
            changes.setdefault(path, lines)
    return changes


def _asking_git[T](option: str, needs: str, ask: Callable[[], T]) -> T:
    try:
        return ask()
    except GitStatusError as exc:
        raise _Stop(f"dreck: {option} needs {needs}: {exc}") from exc


def _select(root: Path, options: Options) -> tuple[list[Path], ChangedLines | None]:
    """The files to score, kept to those git reports as changed when an option
    asks, and the changed lines when `--changed-functions` asks."""

    searched, fragments = _split(root, options.positionals)
    files = select(root, searched, fragments)
    if options.changed_functions:
        changes = _asking_git("--changed-functions", "git", lambda: _changed_lines(root, searched))
        return [path for path in files if path in changes], changes
    if options.changed:
        changed = _asking_git(
            "--changed",
            "git status",
            lambda: set().union(*(changed_files(folder) for folder in _git_folders(root, searched))),
        )
        files = [path for path in files if path in changed]
    return files, None


def _touched(entries: list[Entry], root: Path, changes: ChangedLines) -> list[Entry]:
    """The entries whose line range holds a changed line."""

    by_file = {display_path(path, root): lines for path, lines in changes.items()}
    return [
        entry
        for entry in entries
        if (lines := by_file.get(entry.path, set())) is None
        or any(entry.start_line <= line <= entry.end_line for line in lines)
    ]


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _warn(functions, coverage, missed, changed: bool) -> None:
    """Name each given path that holds none of the functions, then hint at the reports each uncovered language needs.

    With `changed`, only changed files are scored, so a report older than them is one more cause.
    """

    if coverage is None:
        return
    causes = "another checkout or for another project" + (", or before the files changed" if changed else "")
    for path in unmatched(functions, coverage):
        print(
            f"dreck: --coverage-report {path}: matches none of the files being scored; was it made in {causes}?",
            file=sys.stderr,
        )
    for spec in missed:
        print(
            f"dreck: {spec.name}: coverage and CRAP show -; no coverage report given matches its files. "
            f"Pass --coverage-report <{spec.reports}>.",
            file=sys.stderr,
        )


def run(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    try:
        options = parse_args(list(sys.argv[1:] if argv is None else argv))
    except ValueError as exc:
        print(f"{exc}\n\n{help_text()}", file=sys.stderr, end="")
        return 1
    if options.help:
        print(help_text(), end="")
        return 0
    root = Path.cwd()
    try:
        files, changes = _select(root, options)
    except _Stop as exc:
        print(exc, file=sys.stderr)
        return 1
    if not files:
        print("No source files to analyze.")
        entries, unreadable, broken = [], [], []
    else:
        try:
            coverage = load(options.reports, files, root) if options.reports else None
        except ReportError as exc:
            print(exc, file=sys.stderr)
            return 1
        functions, broken, unreadable = read_files(files, root)
        for file in unreadable:
            print(f"dreck: {file} cannot be read; skipped", file=sys.stderr)
        for file in broken:
            print(f"dreck: {file} has parse errors; scored as parsed", file=sys.stderr)
        # Scored over every function of the selected files, so a language
        # counts as covered as it would without --changed-functions.
        entries, missed = scored(functions, coverage)
        if changes is not None:
            entries = _touched(entries, root, changes)
        print(render(worst_first(entries)), end="", flush=True)
        _warn(functions, coverage, missed, options.changed or options.changed_functions)
    print(
        f"dreck: {_counted(len(files) - len(unreadable), 'file')} scanned, "
        f"{_counted(len(entries), 'function')} scored, "
        f"{_counted(len(broken), 'file')} with parse errors, "
        f"{time.perf_counter() - started:.2f}s",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> None:
    sys.exit(run(argv))
