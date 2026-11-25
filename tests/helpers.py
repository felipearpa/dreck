# Adapted from doppel's tests/helpers.py.
import re
import subprocess
from pathlib import Path


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def functions(spec, source: str, path: str) -> list:
    """The functions `spec` reads in `source`, parse errors or not."""

    found, _has_error = spec.functions(source, path)
    return found


def complexity_in(spec, source: str, path: str, name: str) -> int:
    return {fn.name: fn.complexity for fn in functions(spec, source, path)}[name]


LINE = re.compile(r"crap (\S+)  cc (\d+)  cov (\S+)  (\S+):(\d+)-(\d+)  (.+)")


def scores(out: str) -> dict[tuple[str, int], tuple[str, str]]:
    """Coverage and CRAP of each printed line, keyed by name and first line."""

    found = {}
    for line in out.splitlines():
        match = LINE.fullmatch(line)
        assert match, line
        found[(match[7], int(match[5]))] = (match[3], match[1])
    return found


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=dreck", "-c", "user.email=dreck@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def commit_all(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "committed")
