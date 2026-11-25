# Ported from crapper's tests/test_kotlin.py, without its namespace assertions, and doppel's tests/test_kotlin.py (the walk).
from pathlib import Path

from dreck.discover import source_files
from dreck.languages.kotlin import SPEC
from helpers import complexity_in, functions, write


PATH = "src/main/kotlin/demo/Board.kt"


def read(source, path=PATH):
    return functions(SPEC, source, path)


def entries(source, path=PATH):
    return [(fn.name, fn.jvm_class) for fn in read(source, path)]


def complexity_of(body, name="choose"):
    return complexity_in(SPEC, f"package demo\n\n{body}", "Demo.kt", name)


def test_when_reading_then_top_level_type_and_companion_functions_are_found():
    source = """
package com.demo.app

fun place(x: Int): Int = x + 1

fun String.shout(): String {
    return uppercase()
}

class Board {
    fun open() {}

    class Cell {
        fun mark() {}
    }

    object Rules {
        fun check() {}
    }

    companion object {
        fun create(): Board = Board()
    }
}

class Widget {
    companion object Factory {
        fun make() {}
    }
}

object Registry {
    fun lookup() {}
}
"""
    assert entries(source) == [
        ("place", "com.demo.app.BoardKt"),
        ("shout", "com.demo.app.BoardKt"),
        ("open", "com.demo.app.Board"),
        ("mark", "com.demo.app.Board$Cell"),
        ("check", "com.demo.app.Board$Rules"),
        ("create", "com.demo.app.Board$Companion"),
        ("make", "com.demo.app.Widget$Factory"),
        ("lookup", "com.demo.app.Registry"),
    ]


def test_given_a_file_jvm_name_or_lower_case_stem_when_reading_then_they_name_the_top_level_class():
    named = '@file:JvmName("Utilities")\npackage demo\n\nfun run() = 1\n'
    assert entries(named) == [("run", "demo.Utilities")]
    lower = "package demo\n\nfun run() = 1\n"
    assert entries(lower, "src/main/kotlin/demo/featureFromLayout.kt") == [
        ("run", "demo.FeatureFromLayoutKt")
    ]


def test_given_no_package_when_reading_then_the_class_is_the_file_stem():
    source = "fun run() = 1\n\nclass Board {\n    fun open() {}\n}\n"
    assert entries(source, "scripts/tools.kt") == [
        ("run", "ToolsKt"),
        ("open", "Board"),
    ]


def test_given_an_enum_value_with_a_body_when_reading_then_it_adds_a_type_level():
    source = """
package demo

enum class Shape {
    CIRCLE { override fun area() = 3.14 },
    SQUARE { override fun area(): Double { return 1.0 } },
    PLAIN;

    open fun area(): Double = 0.0
}
"""
    assert entries(source) == [
        ("area", "demo.Shape$CIRCLE"),
        ("area", "demo.Shape$SQUARE"),
        ("area", "demo.Shape"),
    ]


def test_when_reading_then_only_outer_functions_with_a_body_are_found():
    source = """
package demo

abstract class Shape(val size: Int) {
    constructor() : this(1)

    init {
        println(size)
    }

    val area: Int
        get() = size * size

    abstract fun draw()

    fun render() {
        fun local() {}
        val handler = { x: Int -> x }
        val runner = object : Runnable {
            override fun run() {}
        }
        listOf(1).forEach(fun(item) { println(item) })
    }
}

interface Drawable {
    fun paint()
}
"""
    assert entries(source) == [("render", "demo.Shape")]


def test_when_reading_then_functions_carry_their_lines_and_path():
    source = "package demo\n\nfun run(): Int {\n    return 1\n}\n"
    (found,) = read(source, "app/Board.kt")
    assert (found.start_line, found.end_line, found.path) == (3, 5, "app/Board.kt")


def test_given_no_decision_when_scoring_then_complexity_is_one():
    assert complexity_of("fun choose() = 1\n") == 1


def test_given_each_decision_kind_when_scoring_then_each_adds_one():
    body = """
fun choose(a: Int?, items: List<Int>): Int {
    if (a == null) return 0
    for (item in items) {}
    while (false) {}
    do {} while (false)
    try {
        println(a)
    } catch (e: IllegalStateException) {
    }
    val b = a > 1 && a < 5
    val c = a > 9 || a < 0
    val d = items.firstOrNull() ?: 0
    val e = items.firstOrNull()?.plus(1)
    return d
}
"""
    assert complexity_of(body) == 10


def test_given_when_arms_when_scoring_then_each_adds_one_but_else():
    body = """
fun choose(x: Int): Int = when (x) {
    1 -> 10
    2, 3 -> 20
    in 4..9 -> 30
    else -> 0
}
"""
    assert complexity_of(body) == 4


def test_given_nested_decisions_when_scoring_then_they_count_in_the_outer_function():
    body = """
fun choose(items: List<Int>): Int {
    fun pick(x: Int) = if (x > 1) x else 0
    val kept = items.filter { it > 0 && it < 9 }
    val runner = object : Runnable {
        override fun run() {
            if (kept.isEmpty()) println("none")
        }
    }
    return kept.size
}
"""
    assert complexity_of(body) == 4


def test_given_an_annotated_function_type_when_reading_then_nothing_after_it_is_lost():
    source = """
package demo

@Composable
fun Frame(content: @Composable () -> Unit, slot: @Composable (() -> Unit)? = null) {
    if (slot != null) slot()
    content()
}

@Preview
@Composable
private fun FramePreview() {
    Frame {}
}
"""
    found, has_error = SPEC.functions(source, "Frame.kt")
    assert [(fn.name, fn.start_line, fn.complexity) for fn in found] == [
        ("Frame", 4, 2),
        ("FramePreview", 10, 1),
    ]
    assert not has_error


def test_given_a_broken_file_when_reading_then_it_says_so_and_keeps_what_it_read():
    found, has_error = SPEC.functions("fun run() {\n    return 1\n}\n\nfun broken( {\n", "Broken.kt")
    assert has_error
    assert "run" in [fn.name for fn in found]


def test_when_walking_then_build_output_tests_and_scripts_are_skipped(tmp_path, monkeypatch):
    for name in [
        "src/main/kotlin/Keep.kt",
        "src/main/kotlin/com/acme/build/Builder.kt",
        "src/commonMain/kotlin/KeepToo.kt",
        "feature/src/androidMain/kotlin/Contest.kt",
        "build/generated/Generated.kt",
        "app/build/tmp/Stub.kt",
        ".gradle/cache/Cached.kt",
        ".git/objects/Tracked.kt",
        "src/commonTest/kotlin/Shared.kt",
        "src/test/kotlin/Unit.kt",
        "feature/src/androidTest/kotlin/Device.kt",
        "feature/src/testFixtures/kotlin/Fake.kt",
        "feature/testutils/Helper.kt",
        "checkout/build/src/main/kotlin/Keep.kt",
        "src/main/kotlin/FooTest.kt",
        "src/main/kotlin/FooTests.kt",
        "src/main/kotlin/FooSpec.kt",
        "build.gradle.kts",
    ]:
        write(tmp_path, name, "")

    def walked(folder: Path) -> list[str]:
        return [path.relative_to(tmp_path.resolve()).as_posix() for path in source_files(folder)]

    assert walked(tmp_path) == [
        "feature/src/androidMain/kotlin/Contest.kt",
        "feature/testutils/Helper.kt",
        "src/commonMain/kotlin/KeepToo.kt",
        "src/main/kotlin/Keep.kt",
        "src/main/kotlin/com/acme/build/Builder.kt",
    ]
    # A package folder called `build` under `src` is code; `app/build` beside a module's `src` is not.
    src_kept = [
        "src/commonMain/kotlin/KeepToo.kt",
        "src/main/kotlin/Keep.kt",
        "src/main/kotlin/com/acme/build/Builder.kt",
    ]
    assert walked(tmp_path / "src") == src_kept
    assert walked(tmp_path / "feature" / "src") == ["feature/src/androidMain/kotlin/Contest.kt"]
    # The walked folder's name is a possible `src` parent, never a reason to skip.
    assert walked(tmp_path / "feature") == [
        "feature/src/androidMain/kotlin/Contest.kt",
        "feature/testutils/Helper.kt",
    ]
    # A project called `build`, walked from inside or named, is scanned however it is spelled.
    checkout = ["checkout/build/src/main/kotlin/Keep.kt"]
    assert walked(tmp_path / "checkout" / "build") == checkout
    assert walked(tmp_path / "checkout" / "build" / "src" / "main") == checkout
    monkeypatch.chdir(tmp_path / "src")
    assert walked(Path(".")) == walked(Path.cwd()) == src_kept
    monkeypatch.chdir(tmp_path / "checkout" / "build")
    assert walked(Path(".")) == walked(Path.cwd()) == checkout
