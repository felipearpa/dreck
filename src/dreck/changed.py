# Copied from doppel's src/doppel/changed.py, adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/cli.py (0BSD).
"""What git reports as changed: the files, for `--changed`, and the lines, for `--changed-functions`."""

from __future__ import annotations

import codecs
import os
import re
import subprocess
from pathlib import Path


class GitStatusError(Exception):
    pass


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", os.fspath(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _command(args: tuple[str, ...]) -> str:
    """The git command in `args`, past any leading `-c name=value`."""

    while args[0] == "-c":
        args = args[2:]
    return args[0]


def _git(root: Path, *args: str) -> bytes:
    result = _run(root, *args)
    if result.returncode != 0:
        raise GitStatusError(os.fsdecode(result.stderr).strip() or f"git {_command(args)} failed")
    return result.stdout


def _status(folder: Path) -> tuple[Path, list[tuple[bytes, Path]]]:
    """The repository top, and each existing changed file with its two-letter status code.

    `-z` keeps spaces and non-ASCII names intact. A missing path, including a
    deletion, is left out. A rename is the new file only. Ignored files are
    not reported by git, so they are not changed.
    """

    top = Path(os.fsdecode(_git(folder, "rev-parse", "--show-toplevel")).strip())
    status = _git(folder, "status", "--porcelain", "-z", "--no-renames", "--untracked-files=all")
    found: list[tuple[bytes, Path]] = []
    for entry in status.split(b"\0"):
        if len(entry) <= 3:
            continue
        path = (top / os.fsdecode(entry[3:])).resolve()
        if path.is_file():
            found.append((entry[:2], path))
    return top, found


def changed_files(folder: Path) -> set[Path]:
    """Added, modified and untracked files in the repository holding `folder`, resolved."""

    _top, found = _status(folder)
    return {path for _code, path in found}


# A changed file's changed lines. None means every line: an untracked file.
ChangedLines = dict[Path, set[int] | None]

_HUNK = re.compile(rb"@@ -\S+ \+(\d+)(?:,(\d+))? @@")


def _diff_path(header: bytes) -> str | None:
    """The new-side path of a `+++ ` header, or None for a deleted file.

    git ends the header with a tab when the name holds a space, and quotes a
    name holding a quote, a backslash or a control character.
    """

    name = header[4:].rstrip(b"\t")
    if name == b"/dev/null":
        return None
    if name.startswith(b'"') and name.endswith(b'"'):
        name = codecs.escape_decode(name[1:-1])[0]
    return os.fsdecode(name[2:] if name.startswith(b"b/") else name)


def _hunk_lines(line: bytes) -> range:
    """New-side lines of one `-U0` hunk. A pure deletion touches the line above it."""

    match = _HUNK.match(line)
    if match is None:
        return range(0)
    start = int(match.group(1))
    count = 1 if match.group(2) is None else int(match.group(2))
    if count == 0:
        return range(max(start, 1), max(start, 1) + 1)
    return range(start, start + count)


def _parse_diff(top: Path, diff: bytes, changes: ChangedLines) -> None:
    current: Path | None = None
    in_header = False
    for line in diff.split(b"\n"):
        if line.startswith(b"diff --git "):
            in_header, current = True, None
        elif in_header and line.startswith(b"+++ "):
            name = _diff_path(line)
            current = None if name is None else (top / name).resolve()
        elif line.startswith(b"@@"):
            in_header = False
            if current is not None and changes.get(current, set()) is not None:
                changes.setdefault(current, set()).update(_hunk_lines(line))


def changed_lines(folder: Path) -> ChangedLines:
    """Lines changed since HEAD in the repository holding `folder`, from `git diff -U0 HEAD`.

    An untracked file is wholly changed, and so is every changed file before the first commit.
    """

    top, found = _status(folder)
    if _run(folder, "rev-parse", "--verify", "--quiet", "HEAD").returncode != 0:
        return {path: None for _code, path in found}
    changes: ChangedLines = {path: None for code, path in found if code == b"??"}
    diff = _git(
        folder,
        "-c",
        "core.quotePath=false",
        "diff",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        "--no-renames",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        "--no-relative",
        "HEAD",
    )
    _parse_diff(top, diff, changes)
    return {path: lines for path, lines in changes.items() if path.is_file()}
