# Adapted from doppel's src/doppel/scan.py, adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/scan.py (0BSD).
from __future__ import annotations

from pathlib import Path

from dreck.discover import spec_of
from dreck.model import Function
from dreck.paths import display_path


def read_files(files: list[Path], root: Path) -> tuple[list[Function], list[str], list[str]]:
    """The functions read, the files the grammar could not fully parse, and
    the files that could not be read.

    A file with parse errors is scored as parsed; an unreadable one is left out.
    """

    functions: list[Function] = []
    broken: list[str] = []
    unreadable: list[str] = []
    for path in files:
        spec = spec_of(path)
        if spec is None:
            continue
        file = display_path(path, root)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            unreadable.append(file)
            continue
        found, has_error = spec.functions(source, file)
        if has_error:
            broken.append(file)
        functions.extend(found)
    return functions, broken, unreadable
