"""The engine names no language: everything about one lives in its spec, `languages/<language>.py`."""

import re
from pathlib import Path

import pytest

import dreck
from dreck.discover import specs

ENGINE = sorted(Path(dreck.__file__).parent.glob("*.py"))
LANGUAGES = sorted(Path(dreck.__file__).parent.joinpath("languages").glob("[!_]*.py"))
# The ways a first line names the file its code came from.
ORIGIN = re.compile(r"# (?:Copied|Adapted|Ported|Reader adapted) from ")


def naming(text: str) -> list[str]:
    """The language names, module names and file extensions `text` holds,
    leaving out a first-line comment naming the file the code came from."""

    lines = text.splitlines()
    if lines and ORIGIN.match(lines[0]):
        lines = lines[1:]
    body = "\n".join(lines)
    words = {spec.name for spec in specs()} | {path.stem for path in LANGUAGES}
    found = [word for word in sorted(words) if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", body, re.IGNORECASE)]
    extensions = {extension for spec in specs() for extension in spec.extensions}
    found += [extension for extension in sorted(extensions) if re.search(rf"{re.escape(extension)}(?!\w)", body)]
    return found


@pytest.mark.parametrize("module", ENGINE, ids=lambda path: path.name)
def test_given_an_engine_module_when_read_then_it_names_no_language(module):
    assert naming(module.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "line",
    ['LABEL = "Kotlin"', "# swift needs this", "path = 'Board.fs'", 'name = "F#"', "from dreck.languages import fsharp"],
)
def test_given_a_language_name_below_the_first_line_when_searched_then_it_is_found(line):
    assert naming(f"# Adapted from somewhere.\n{line}\n") != []


@pytest.mark.parametrize("line", ["# Swift only", "# kotlin helpers"])
def test_given_a_first_line_comment_that_names_no_origin_when_searched_then_its_language_is_found(line):
    assert naming(f"{line}\nx = 1\n") != []


def test_given_a_first_line_origin_comment_when_searched_then_its_language_is_allowed():
    assert naming("# Adapted from crapper's src/crapper/languages/swift_coverage.py (0BSD).\nx = 1\n") == []
