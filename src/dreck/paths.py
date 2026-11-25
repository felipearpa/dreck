# Adapted from doppel's src/doppel/scan.py, adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/scan.py (0BSD).
"""How a path prints. Imports nothing else from dreck, so any module can use it."""

from __future__ import annotations

from pathlib import Path


def display_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
