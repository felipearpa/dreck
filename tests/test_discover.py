# Adapted from doppel's tests/test_cli.py (its extra spec file test).
from dreck.discover import source_files, spec_of, specs
from helpers import write


def test_given_an_extra_language_file_when_walking_then_its_files_are_found(stand_in, tmp_path):
    project = tmp_path / "project"
    for name in ["a/One.si", "a/Two.sin", "skipped/Three.si", "notes.txt"]:
        write(project, name, "")

    found = [path.relative_to(project.resolve()).as_posix() for path in source_files(project)]

    assert found == ["a/One.si", "a/Two.sin"]
    assert spec_of(project / "a/One.si").name == "Standin"
    assert "Standin" in [spec.name for spec in specs()]


def test_given_source_under_a_folder_any_language_prunes_when_walking_then_it_is_not_scored(tmp_path):
    project = tmp_path / "project"
    pruned = [
        ".build/checkouts/Lib/src/main/kotlin/Lib.kt",
        "obj/Gen.kt",
        "DerivedData/Gen.kt",
        "Pods/Lib/Lib.kt",
        "Carthage/Checkouts/Lib/Lib.kt",
        ".gradle/caches/Gen.swift",
        "bin/Debug/Gen.swift",
    ]
    for name in ["src/main/kotlin/Board.kt", *pruned]:
        write(project, name, "fun f() {}\n")

    found = [path.relative_to(project.resolve()).as_posix() for path in source_files(project)]

    assert found == ["src/main/kotlin/Board.kt"]

