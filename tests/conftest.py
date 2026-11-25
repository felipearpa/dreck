# The stand-in language adapted from doppel's tests/test_cli.py.
import sys

import pytest

import dreck.languages
from dreck.discover import specs
from helpers import write

STAND_IN_SPEC = """\
from dreck.coverage import BY_JVM_CLASS
from dreck.model import Function
from dreck.spec import LanguageSpec

SPEC = LanguageSpec(
    name="Standin",
    extensions=frozenset({".si", ".sin"}),
    skips=lambda path: "skipped" in path.parts[1:],
    functions=lambda source, path: (
        [
            Function(name=name, complexity=1, start_line=number, end_line=number, path=path)
            for number, name in enumerate(source.splitlines(), start=1)
            if name
        ],
        False,
    ),
    reports="a stand-in report",
    lookup=BY_JVM_CLASS,
)
"""


@pytest.fixture
def stand_in(tmp_path, monkeypatch):
    """A language file `standin` (`.si`, `.sin`, skipping `skipped` folders) in a
    folder of its own, appended to the languages package and listed nowhere.

    Each line of a file is a function named by it; no report holds one.
    """

    folder = tmp_path / "extra"
    write(folder, "standin.py", STAND_IN_SPEC)
    monkeypatch.setattr(dreck.languages, "__path__", [*dreck.languages.__path__, str(folder)])
    monkeypatch.delitem(sys.modules, "dreck.languages.standin", raising=False)
    specs.cache_clear()
    yield
    specs.cache_clear()
