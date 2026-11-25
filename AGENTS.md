# dreck

A command-line tool that scores the complexity, coverage and CRAP of each function, worst first, with its location. Python, parsed with tree-sitter through `tree-sitter-language-pack`, managed with uv. Cut from [crapper](https://github.com/felipearpa/crapper) in the shape of [doppel](https://github.com/felipearpa/doppel).

## Commands

- Install: `uv sync` (needs network; the language pack downloads each parser on first use, so the first run in each language needs network too).
- Test: `uv run pytest`
- Run: `uv run dreck [path-or-fragment ...]` (scores the current directory when no path is given).

## Rules

- The README changes with behavior: a change to what dreck reports, its options or its output updates the README in the same change.
- The engine (`src/dreck/*.py`) names no language. Everything about one language lives in its spec, `src/dreck/languages/<language>.py`, and its tests.
- `tree-sitter-language-pack` is pinned to an exact version in `pyproject.toml` and `uv.lock`: an upgrade can rename grammar nodes and silently change scores, so upgrade it on purpose and rerun the tests.
- dreck writes no file: a run reads and prints, nothing more.
- Files copied or adapted from crapper or doppel keep their first-line comment naming the file they came from.
- Code uses short, meaningful names. A comment that repeats what a name already says is removed; comments stay where they say why, record a grammar quirk, or name the file the code came from.
