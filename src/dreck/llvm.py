# Adapted from crapper's src/crapper/languages/swift_coverage.py (0BSD), taking the selected files as they are.
"""Line counts from LLVM's coverage tools: Xcode derived data and llvm-cov JSON exports.

Derived data given by path, or one folder above it, is read by
`read_derived_data`: each profile it holds (`Build/ProfileData/<device>/*.profdata`)
is read with `xcrun llvm-cov export -format=lcov` against the test bundles
and apps built next to it, which also holds the packages linked into them;
`xccov` reports those packages as empty. Only the lines `llvm-cov` lists,
which are the executable ones, are kept, because a line it leaves out is not
code. Only the selected files are kept, under their absolute paths, so a test
or third-party file cannot match a source file by suffix. A file in several
profiles, or in several binaries, is added up line by line, so a line is
covered when any of them covered it. A profile that cannot be converted, or
no `xcrun`, as on Linux, raises `ConversionError`.

An llvm-cov JSON export is read by `read_export` without `xcrun`. Its
per-line counts are derived from each file's segments the way `llvm-cov`
derives its own LCOV lines; text that is not such an export, or an export of
an unexpected shape, raises ValueError.

Both return each selected file's line counts, by absolute path, and write
nothing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_PROFILES = ("Build/ProfileData/*/*.profdata", "*/Build/ProfileData/*/*.profdata")
_BINARIES = ("*/*.xctest", "*/*.app", "*/*.app/PlugIns/*.xctest")
_EXPORT_TYPE = "llvm.coverage.json.export"

Counts = dict[str, dict[int, int]]


class ConversionError(Exception):
    """Xcode derived data that cannot be converted, with the reason."""


def _selected(files: list[Path]) -> dict[str, str]:
    """Each selected file by its real path, mapped to the path written."""

    return {os.path.realpath(file): str(Path(file).resolve()) for file in files}


def _profiles(folder: Path) -> list[Path]:
    return sorted({path for pattern in _PROFILES for path in folder.glob(pattern)})


def _bundle_binaries(bundle: Path) -> list[Path]:
    """The bundle's executable, and the `.debug.dylib` that holds an app's code in a debug build."""

    found = []
    for folder in (bundle, bundle / "Contents" / "MacOS"):
        for name in (bundle.stem, f"{bundle.stem}.debug.dylib"):
            if (folder / name).is_file():
                found.append(folder / name)
    return found


def _binaries(profile: Path) -> list[Path]:
    """Test bundles, hosted test bundles, and apps in the `Build/Products` next to the profile."""

    products = profile.parents[2] / "Products"
    bundles = sorted({path for pattern in _BINARIES for path in products.glob(pattern)})
    return [binary for bundle in bundles for binary in _bundle_binaries(bundle)]


def _archs(binary: Path) -> list[str]:
    try:
        completed = subprocess.run(["xcrun", "lipo", "-archs", str(binary)], capture_output=True, text=True)
    except OSError:
        return []
    return completed.stdout.split() if completed.returncode == 0 else []


def _arch_options(binaries: list[Path]) -> list[list[str]]:
    """The `-arch` to follow each binary with, or none at all.

    `llvm-cov` refuses a universal binary, even one with a single slice such
    as Xcode's UI test runner, without `-arch`, and pairs the `-arch` options
    with the binaries in order, so every binary gets its own: `arm64` if it
    has that slice, its first slice otherwise. When `lipo` cannot read one
    binary, none gets an `-arch`.
    """

    archs = [_archs(binary) for binary in binaries]
    unread = [str(binary) for binary, found in zip(binaries, archs) if not found]
    if unread:
        print(
            f"dreck: lipo could not read the architecture of {', '.join(unread)}; llvm-cov gets no -arch.",
            file=sys.stderr,
        )
        return [[] for _ in binaries]
    return [[f"-arch={'arm64' if 'arm64' in found else found[0]}"] for found in archs]


def _export(profile: Path, binaries: list[Path]) -> str:
    options = _arch_options(binaries)
    command = [
        "xcrun", "llvm-cov", "export", "-format=lcov", "-skip-functions",
        "-instr-profile", str(profile), str(binaries[0]), *options[0],
    ]
    for binary, arch in zip(binaries[1:], options[1:]):
        command.extend(["-object", str(binary), *arch])
    try:
        completed = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        raise ConversionError(f"{profile}: llvm-cov failed to start ({exc})") from exc
    if completed.returncode != 0:
        raise ConversionError(f"{profile}: llvm-cov exited {completed.returncode} ({completed.stderr.strip()})")
    return completed.stdout


def _counts_for(merged: Counts, path: str, selected: dict[str, str]) -> dict[int, int] | None:
    source = selected.get(os.path.realpath(path))
    return None if source is None else merged.setdefault(source, {})


def _add_lcov(merged: Counts, text: str, selected: dict[str, str]) -> None:
    counts: dict[int, int] | None = None
    for line in text.splitlines():
        if line.startswith("SF:"):
            counts = _counts_for(merged, line[3:], selected)
        elif line.startswith("DA:") and counts is not None:
            number, hits = line[3:].split(",")[:2]
            counts[int(number)] = counts.get(int(number), 0) + int(hits)
        elif line == "end_of_record":
            counts = None


def _line_counts(segments: list) -> dict[int, int]:
    """Each executable line's count, as `llvm-cov`'s line coverage iterator gives it.

    A segment is `[line, column, count, hasCount, isRegionEntry, isGapRegion]`.
    A line is executable when a counted region starts on it, or when the
    segment carried over from an earlier line has a count; its count is the
    highest of those. A line that starts a skipped region is not executable.
    """

    counts: dict[int, int] = {}
    if not segments:
        return counts
    by_line: dict[int, list] = {}
    for segment in segments:
        by_line.setdefault(segment[0], []).append(segment)
    wrapped = None
    for number in range(segments[0][0], segments[-1][0] + 1):
        starting = by_line.get(number, [])
        starts = [s for s in starting if s[3] and s[4] and not s[5]]
        skipped = bool(starting) and not starting[0][3] and starting[0][4]
        mapped = not skipped and (bool(wrapped and wrapped[3]) or bool(starts))
        mapped = mapped or any(s[3] and s[4] for s in starting)
        if mapped:
            counts[number] = max([wrapped[2] if wrapped else 0, *(s[2] for s in starts)])
        if starting:
            wrapped = starting[-1]
    return counts


def read_export(text: str, files: list[Path]) -> Counts:
    """The selected files' line counts in an llvm-cov JSON export; ValueError when it is not one."""

    selected = _selected(files)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"not an llvm-cov JSON export ({exc})") from exc
    if not isinstance(data, dict) or data.get("type") != _EXPORT_TYPE:
        raise ValueError(f"not an llvm-cov JSON export (no type {_EXPORT_TYPE})")
    read: Counts = {}
    try:
        for unit in data.get("data", []):
            for file in unit.get("files", []):
                counts = _counts_for(read, file["filename"], selected)
                if counts is None:
                    continue
                for number, hits in _line_counts(file.get("segments", [])).items():
                    counts[number] = counts.get(number, 0) + hits
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise ValueError(f"not an llvm-cov JSON export ({exc!r})") from exc
    return read


def is_derived_data(folder: Path) -> bool:
    """Whether `folder`, or a folder directly inside it, is Xcode derived data with a profile."""

    return folder.is_dir() and bool(_profiles(folder))


def read_derived_data(folder: Path, files: list[Path]) -> Counts:
    """The selected files' line counts in the derived data at `folder`, or one folder down.

    Nothing is written. Raises ConversionError when a profile cannot be converted.
    """

    selected = _selected(files)
    profiles = _profiles(folder)
    if shutil.which("xcrun") is None:
        names = ", ".join(str(profile) for profile in profiles)
        raise ConversionError(f"xcrun is not installed, so the Xcode coverage profiles {names} cannot be read")
    merged: Counts = {}
    for profile in profiles:
        binaries = _binaries(profile)
        if not binaries:
            raise ConversionError(f"{profile}: no test bundle or app next to it")
        _add_lcov(merged, _export(profile, binaries), selected)
    return merged
