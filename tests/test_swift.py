# Ported from crapper's tests/test_swift.py, without its namespace assertions, crapper's tests/test_edges.py (its Swift skip cases) and doppel's tests/test_swift.py (the walk).
from pathlib import Path

import pytest

from dreck.discover import source_files
from dreck.languages.swift import SPEC
from helpers import complexity_in, functions, write


PATH = "App/Views/Board.swift"


def read(source, path=PATH):
    return functions(SPEC, source, path)


def entries(source, path=PATH):
    return [fn.name for fn in read(source, path)]


def complexity_of(body, name="choose"):
    return complexity_in(SPEC, body, "Demo.swift", name)


def test_when_reading_then_functions_methods_initializers_and_deinitializers_are_entries():
    source = """
func place() {}

final class Board {
    init(size: Int) { self.size = size }
    init?(text: String) { return nil }
    deinit { print("bye") }
    func open() {}
    static func make() -> Board { Board(size: 1) }
}
"""
    assert entries(source) == [
        "place",
        "init",
        "init",
        "deinit",
        "open",
        "make",
    ]


def test_given_properties_with_a_body_when_reading_then_each_is_one_entry():
    source = """
struct Cell {
    var size: Int
    let label = "cell"
    var area: Int {
        get { size * size }
        set { size = newValue }
    }
    var body: some View { Text(label) }
    var watched: Int = 0 {
        willSet { print(newValue) }
        didSet { print(oldValue) }
    }
    lazy var cache: [Int] = { [size] }()
    subscript(index: Int) -> Int { index }
}
"""
    assert entries(source) == [
        "area",
        "body",
        "watched",
        "cache",
        "subscript",
    ]


def test_given_nested_functions_closures_and_requirements_when_reading_then_none_is_an_entry():
    source = """
protocol Drawable {
    var size: Int { get }
    init(size: Int)
    func draw()
}

struct Shape {
    func render() {
        func local() {}
        let handler = { (x: Int) in x }
        struct Local {
            func inner() {}
        }
        handler(1)
    }
}
"""
    assert entries(source) == ["render"]


def test_when_reading_then_entries_carry_their_lines_and_path():
    source = "struct Board {\n    func run() -> Int {\n        return 1\n    }\n}\n"
    (found,) = read(source, "Board.swift")
    assert (found.start_line, found.end_line, found.path) == (2, 4, "Board.swift")


def test_given_no_decision_when_scoring_then_complexity_is_one():
    assert complexity_of("func choose() -> Int { 1 }\n") == 1


def test_given_each_decision_kind_when_scoring_then_each_adds_one():
    body = """
func choose(a: Int?, items: [Int]) throws -> Int {
    if a == nil { return 0 }
    guard let first = items.first else { return 1 }
    for item in items {}
    while false {}
    repeat {} while false
    do { try check() } catch {}
    let b = first > 1 && first < 5
    let c = first > 9 || first < 0
    let d = a ?? 0
    let e = d > 1 ? 1 : 2
    let f = a?.description
    let g = items.last?[0]
    return d
}
"""
    assert complexity_of(body) == 13


def test_given_commas_between_conditions_when_scoring_then_each_adds_one():
    body = """
func choose(a: Int?, b: Int?, c: Bool) -> Int {
    guard let a, let b, c else { return 0 }
    return a + b
}
"""
    assert complexity_of(body) == 1 + 3
    loop = """
func choose(a: Int, b: Int) {
    if a > 1, b > 1 {}
    while a > 1, b > 1 {}
}
"""
    assert complexity_of(loop) == 5


def test_given_switch_cases_when_scoring_then_each_adds_one_but_default():
    body = """
func choose(x: Shape) -> Int {
    switch x {
    case .circle, .square: return 1
    case .line: return 2
    default: return 0
    }
}
"""
    assert complexity_of(body) == 3


def test_given_a_where_on_a_for_case_or_catch_when_scoring_then_it_adds_one():
    body = """
func choose(items: [Int]) {
    for item in items where item > 0 {}
    switch items.count {
    case let n where n > 3: break
    default: break
    }
    do { try check() } catch let error as Failure where error.fatal {}
}
"""
    assert complexity_of(body) == 7


def test_given_an_if_case_when_scoring_then_it_counts_as_its_if():
    assert complexity_of("func choose(a: Int?) {\n    if case .some(let b) = a { print(b) }\n}\n") == 2


def test_given_try_question_failable_init_commas_and_optionals_when_scoring_then_they_add_nothing():
    source = """
struct Board {
    init?(size: Int?, label: String, items: [Int: String]) {
        let value = try? load(size, label)
        let cast = value as? Int
        print(cast, items)
    }
}
"""
    (found,) = read(source, "Board.swift")
    assert found.complexity == 1


def test_given_closure_and_nested_function_decisions_when_scoring_then_they_count_in_the_outer_entry():
    body = """
func choose(items: [Int]) -> Int {
    func pick(_ x: Int) -> Int { x > 1 ? x : 0 }
    let kept = items.filter { $0 > 0 && $0 < 9 }
    return kept.isEmpty ? 0 : pick(kept[0])
}
"""
    assert complexity_of(body) == 4


def test_given_property_bodies_when_scoring_then_their_decisions_count():
    source = """
struct Cell {
    var label: String {
        get { size > 1 ? "big" : "small" }
        set { if newValue.isEmpty { size = 0 } }
    }
    var watched: Int = 0 {
        didSet { if oldValue != watched { refresh() } }
    }
}
"""
    found = {fn.name: fn.complexity for fn in read(source, "Cell.swift")}
    assert found == {"label": 3, "watched": 2}


def test_given_an_empty_tuple_argument_when_reading_then_the_next_function_keeps_its_lines():
    source = """
final class Loader {
    func finish(continuation: Continuation) {
        continuation.resume(returning: (()))
        completion(.success(()))
    }

    func next() -> Int {
        if ready { return 1 }
        return 0
    }
}
"""
    found = [(fn.name, fn.start_line, fn.end_line, fn.complexity) for fn in read(source, "Loader.swift")]
    assert found == [("finish", 3, 6, 1), ("next", 8, 11, 2)]


def test_given_an_initializer_with_a_multi_line_where_when_reading_then_its_body_is_kept():
    source = """
struct Paging<Data, Content> {
    init(data: Data, content: Content) where Data: RandomAccessCollection,
        Content: View {
        if data.isEmpty { print("empty") }
        self.data = data
    }

    func after() {}
}
"""
    found = [(fn.name, fn.start_line, fn.end_line, fn.complexity) for fn in read(source, "Paging.swift")]
    assert found == [("init", 3, 7, 2), ("after", 9, 9, 1)]


@pytest.mark.parametrize(
    "parameters",
    [
        'x: String = ")", y: String = "\\")", z: String = \"\"\"\n    )\n    \"\"\"',
        'p: String = #"C:\\"#',
        'p: String = #")"#',
        'a: Int, // the "x\n        p: String',
        'a: Int /* ")" */, p: String',
    ],
)
def test_given_a_parenthesis_in_a_string_or_comment_when_reading_then_the_initializer_where_is_still_blanked(parameters):
    source = f"""
struct S {{
    init<T: P, U>({parameters}) where T: P,
        U: Q {{
        if x.isEmpty {{}}
    }}
    func g() {{}}
}}
"""
    found = [(fn.name, fn.complexity) for fn in read(source, "Sources/M/S.swift")]
    assert found == [("init", 2), ("g", 1)]


def test_given_a_where_outside_an_initializer_when_reading_then_it_is_left_as_written():
    source = """
extension Array where Element == Int {
    func total<T>(_ other: T) -> Int where T: Sequence, T.Element == Int {
        for item in other where item > 0 {}
        return 0
    }
}
"""
    (found,) = read(source, "Total.swift")
    assert (found.name, found.complexity) == ("total", 3)


def test_given_a_where_after_an_initializer_call_when_reading_then_it_is_left_as_written():
    source = """
extension Board {
    convenience init(items: [Int]) {
        self.init(size: items.count)
        for item in items where item > 0 {
            print(item)
        }
    }
}
"""
    (found,) = read(source, "Board.swift")
    assert (found.name, found.complexity) == ("init", 3)


def test_given_an_extension_of_a_sugared_type_when_reading_then_its_functions_are_entries():
    source = """
extension [Int] {
    func total() -> Int { 0 }
}

extension [String: Int] {
    func keys() -> Int { 0 }
}

extension Int? {
    func orZero() -> Int { 0 }
}
"""
    assert entries(source, "Feature/Sources/Feature/Sugar.swift") == [
        "total",
        "keys",
        "orZero",
    ]


def test_given_nested_types_and_extensions_when_reading_then_their_functions_are_entries():
    source = """
func helper() {}

enum Feature {
    struct Row {
        func show() {}
    }
}

extension Feature.Row {
    func hide() {}
}

public extension View {
    func card() -> some View { self }
}
"""
    assert entries(source, "Feature/Sources/Feature/Views/Row.swift") == ["helper", "show", "hide", "card"]


def test_given_a_swift_project_when_walking_then_tool_output_tests_and_manifest_are_skipped(tmp_path, monkeypatch):
    for name in [
        "Sources/App/Keep.swift",
        "Sources/App/Contest.swift",
        "App/Feature/KeepToo.swift",
        ".build/checkouts/Dep/Sources/Dep.swift",
        "Packages/Core/.build/release/Gen.swift",
        "target/coverage/swift/DerivedData/SourcePackages/checkouts/Dep/Dep.swift",
        "Pods/Lib/Lib.swift",
        "Carthage/Checkouts/Lib/Lib.swift",
        ".git/objects/Tracked.swift",
        "Tests/AppTests/Unit.swift",
        "AppUITests/Flow.swift",
        "Packages/Core/Tests/CoreTests/Core.swift",
        "Sources/App/FooTests.swift",
        "Package.swift",
        "Packages/Core/Package.swift",
    ]:
        write(tmp_path, name, "")

    def walked(folder: Path) -> list[str]:
        return [path.relative_to(tmp_path.resolve()).as_posix() for path in source_files(folder)]

    assert walked(tmp_path) == [
        "App/Feature/KeepToo.swift",
        "Sources/App/Contest.swift",
        "Sources/App/Keep.swift",
    ]
    # The walked folder's name is context, never a reason to skip; a named file is its own list.
    assert walked(tmp_path / "Tests" / "AppTests") == ["Tests/AppTests/Unit.swift"]
    assert walked(tmp_path / "AppUITests") == ["AppUITests/Flow.swift"]
    assert walked(tmp_path / "Package.swift") == ["Package.swift"]
    monkeypatch.chdir(tmp_path / "AppUITests")
    assert walked(Path(".")) == ["AppUITests/Flow.swift"]


@pytest.mark.parametrize("outer", ["Pods", "DerivedData"])
def test_given_a_project_inside_a_build_folder_name_when_walking_then_its_swift_files_are_kept(tmp_path, outer):
    root = tmp_path / outer / "MyApp"
    for name in ("Sources/App/App.swift", "Pods/Lib/Lib.swift", ".build/checkouts/Dep.swift"):
        write(root, name, "func f() {}\n")
    assert source_files(root) == [(root / "Sources/App/App.swift").resolve()]
