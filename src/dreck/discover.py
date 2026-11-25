# Adapted from doppel's src/doppel/discover.py, adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/discover.py (0BSD).
"""Find the language specs, decide which one owns a file, and walk a folder.

Specs are the modules in the `dreck.languages` folder, each exposing `SPEC`.
Adding a language adds a module there; no list names them.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
from functools import cache
from pathlib import Path, PurePosixPath

from dreck import languages
from dreck.spec import LanguageSpec


@cache
def specs() -> tuple[LanguageSpec, ...]:
    found = []
    for module in pkgutil.iter_modules(languages.__path__):
        found.append(importlib.import_module(f"{languages.__name__}.{module.name}").SPEC)
    return tuple(sorted(found, key=lambda spec: spec.name))


def spec_of(path: Path) -> LanguageSpec | None:
    for spec in specs():
        if path.suffix in spec.extensions:
            return spec
    return None


# Tool and version-control folders: no language's code lives there.
SKIPPED_FOLDERS = frozenset({".git", ".hg", ".svn", ".idea", ".vscode"})


def _skipped(relative: PurePosixPath) -> bool:
    return (
        relative.name in SKIPPED_FOLDERS
        or any(relative.name in spec.prunes for spec in specs())
        or all(spec.skips(relative) for spec in specs())
    )


def _kept(relative: PurePosixPath) -> bool:
    spec = spec_of(Path(relative.name))
    return spec is not None and not spec.skips(relative)


def source_files(root: Path) -> list[Path]:
    """Files under `root` that a spec owns and does not skip (see `LanguageSpec.skips`), sorted.

    A file is its own list, skipped or not.
    """

    # The resolved name, so `.` and the absolute path read the same; "/" for the filesystem root.
    context = root.resolve().name or "/"
    if root.is_file():
        found = [root] if spec_of(root) is not None else []
    else:
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            folder = PurePosixPath(context, Path(dirpath).relative_to(root).as_posix())
            dirnames[:] = [name for name in dirnames if not _skipped(folder / name)]
            found.extend(Path(dirpath) / name for name in filenames if _kept(folder / name))
    return sorted({path.resolve() for path in found}, key=lambda path: path.as_posix())
