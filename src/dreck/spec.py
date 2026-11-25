# Adapted from doppel's src/doppel/spec.py.
"""What a language spec answers. The engine reads these fields and names no language."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from dreck.coverage import Lookup
from dreck.model import Function


@dataclass(frozen=True)
class LanguageSpec:
    """Everything dreck knows about one language.

    `name` is the language as the help and the hints print it.
    `skips` says whether a file or folder under the walked folder is left
    out: test code, build output, dependencies. Its path starts with the
    walked folder's own name, then the path below it (`src/test` when `src`
    is walked). That first part is context only, never a reason to
    skip: a spec may read it as a parent such as `src`, and applies its
    folder and file-name rules to the parts after it.
    `functions` reads the functions of a source file, given its text and its
    path as the report prints it, with their complexity, and says whether the
    grammar could not fully parse the file. A spec parses on its own, since
    some languages rewrite their source before parsing it.
    `reports` names, in words, the reports to pass for the language, for the
    hint printed when no given report covers it. `lookup` finds its functions
    in the reports.
    `prunes` names folders that hold no project source of any language, such
    as a tool's build output or checkouts: the walk enters none below the
    walked folder, whichever language names it.
    """

    name: str
    extensions: frozenset[str]
    skips: Callable[[PurePosixPath], bool]
    functions: Callable[[str, str], tuple[list[Function], bool]]
    reports: str
    lookup: Lookup
    prunes: frozenset[str] = frozenset()
