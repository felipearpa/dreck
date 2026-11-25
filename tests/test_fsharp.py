# Ported from crapper's tests/test_fsharp.py, without its namespace assertions, with the F# skip cases of its tests/test_edges.py.
from pathlib import Path

import pytest

from dreck.discover import source_files
from dreck.languages.fsharp import SPEC
from helpers import complexity_in, functions, write


PATH = "src/Board.fs"


def read(source, path=PATH):
    return functions(SPEC, source, path)


def entries(source, path=PATH):
    return [fn.name for fn in read(source, path)]


def complexity_of(body, name="choose"):
    return complexity_in(SPEC, f"module Demo\n\n{body}", "Demo.fs", name)


def test_when_reading_then_module_functions_nested_modules_and_type_members_are_entries():
    source = """
namespace Demo.Core

module Board =
    let place x = x + 1

    module Inner =
        let tick y = y

type Widget(size: int) =
    let half x = x / 2
    member this.Grow(n) = n + size
    static member Make() = Widget(1)
    member _.Area = size * size
    member val Size = size with get, set
    abstract member Paint: unit -> unit
    interface System.IDisposable with
        member _.Dispose() = ()
"""
    assert entries(source) == ["place", "tick", "half", "Grow", "Make", "Area", "Dispose"]


def test_given_let_rec_and_bindings_and_a_record_member_when_reading_then_each_is_an_entry():
    source = """
module Demo.Http.Routes

let rec even n = if n = 0 then true else odd (n - 1)
and odd n = if n = 0 then false else even (n - 1)

type Point =
    { X: int }
    static member Zero = { X = 0 }
"""
    assert entries(source) == ["even", "odd", "Zero"]


def test_given_no_module_line_when_reading_then_the_functions_are_found():
    source = """
open System

let greet name = "hi " + name
printfn "%s" (greet "x")
"""
    assert entries(source, "src/board.fs") == ["greet"]
    assert entries(source, "scripts/build.fsx") == ["greet"]


def test_given_a_return_type_when_reading_then_the_function_is_an_entry():
    source = """
namespace Demo

module Text =
    let noneIfEmpty (value: string) : string option =
        if value = "" then None else Some value

    let create () : int = 1
    let private twice x : int = x * 2
"""
    found = read(source, "src/Text.fs")
    assert [(fn.name, fn.complexity) for fn in found] == [
        ("noneIfEmpty", 2),
        ("create", 1),
        ("twice", 1),
    ]


def test_given_a_destructured_union_value_when_reading_then_it_is_no_entry():
    source = """
namespace Demo

module Values =
    let Some y = opt
    let Ok (a, b) = r
    let Shape.Circle radius = shape
    let [<Literal>] Some z = opt
    let place x = x + 1
"""
    assert entries(source) == ["place"]
    assert entries("module Demo\n\nlet Some y = opt\nlet Ok (a, b) = r\n") == []


def test_given_a_pascal_case_let_with_arguments_when_reading_then_it_is_a_union_case_pattern():
    source = """
module Demo.Rules

let Validate x = x > 0
let validate x = x > 0
let Handler = fun x -> x + 1
"""
    assert entries(source) == ["validate", "Handler"]


def test_given_an_active_pattern_when_reading_then_its_pattern_text_names_it():
    source = """
module Demo.Numbers

let (|Even|Odd|) n = if n % 2 = 0 then Even else Odd
let inline (|Positive|_|) x = if x > 0 then Some x else None
"""
    assert entries(source) == [
        "|Even|Odd|",
        "|Positive|_|",
    ]


def test_given_a_lambda_bound_to_a_value_when_reading_then_it_is_an_entry():
    source = """
module Demo.Handlers

let handler = fun next ctx -> next ctx
let typed : int -> int = fun x -> x
let wrapped = (fun x -> x + 1)
let pick = function
    | 1 -> "one"
    | _ -> "many"
"""
    assert entries(source) == [
        "handler",
        "typed",
        "wrapped",
        "pick",
    ]


def test_given_nested_lambdas_partials_compositions_and_statements_when_reading_then_none_is_an_entry():
    source = """
module Demo.Values

let limit = 10
let partial = List.map id
let composed = partial >> List.rev
let outer x =
    let inner y = y + 1
    let lam = fun z -> if z then 1 else 0
    inner x + lam true
do printfn "ready"
"""
    assert entries(source) == ["outer"]


def test_given_a_nested_lambda_when_scoring_then_it_counts_in_the_enclosing_function():
    body = """
let choose xs =
    xs |> List.map (fun x -> if x > 0 then x else 0)
"""
    assert complexity_of(body) == 2


def test_given_if_elif_for_and_while_when_scoring_then_each_adds_one():
    body = """
let choose x =
    for i in 1 .. x do ()
    for i = 0 to x do ()
    while x > 0 do ()
    if x > 0 then 1
    elif x = 0 then 0
    else -1
"""
    assert complexity_of(body) == 6


@pytest.mark.parametrize(
    ("short_for", "long_for", "expected"),
    [
        ("[ for i in xs -> i * 2 ]", "[ for i in xs do yield i * 2 ]", 2),
        ("seq { for i in 1 .. 10 -> i }", "seq { for i in 1 .. 10 do yield i }", 2),
        ("[| for i in xs -> if i > 0 then i else 0 |]", "[| for i in xs do yield if i > 0 then i else 0 |]", 3),
    ],
)
def test_given_a_short_for_when_scoring_then_it_adds_one_as_its_long_form(short_for, long_for, expected):
    assert complexity_of(f"let choose xs = {short_for}\n") == expected
    assert complexity_of(f"let choose xs = {long_for}\n") == expected


def test_given_match_function_and_try_arms_when_scoring_then_each_adds_one_but_a_first_arm():
    body = """
let choose x =
    let f = function
        | 1 -> 1
        | _ -> 2
    try
        match x with
        | 1 -> f 1
        | 2 -> 2
        | _ -> 3
    with
    | :? System.ArgumentException -> 0
"""
    assert complexity_of(body) == 5


def test_given_a_when_guard_when_scoring_then_it_adds_one_and_the_first_arm_nothing():
    body = """
let choose x =
    match x with
    | n when n > 2 -> 2
    | _ -> 0
"""
    assert complexity_of(body) == 3


def test_given_and_and_or_when_scoring_then_each_adds_one():
    body = """
let choose a b c =
    a && b || c
"""
    assert complexity_of(body) == 3


def test_given_an_if_condition_when_scoring_then_it_is_no_guard():
    body = """
let choose ready =
    if ready then 1 else 0
"""
    assert complexity_of(body) == 2


def test_given_combinators_and_let_bang_when_scoring_then_they_add_nothing():
    body = """
let choose input =
    task {
        let! value = input |> Option.map (fun x -> x + 1) |> Task.FromResult
        return value
    }
"""
    assert complexity_of(body) == 1


def test_when_reading_then_an_entry_spans_its_definition_lines():
    source = """module Demo

let rec even n =
    n = 0
and odd n =
    n = 1
"""
    found = read(source, "Demo.fs")
    assert [(fn.name, fn.start_line, fn.end_line) for fn in found] == [
        ("even", 3, 4),
        ("odd", 5, 6),
    ]


def test_given_arms_on_one_line_when_scoring_then_each_adds_one_but_a_first_match_arm():
    assert complexity_of("let choose x = match x with | A -> 1 | B -> 2\n") == 2
    assert complexity_of("let choose x = match x with A -> 1 | B -> 2 | C -> 3\n") == 3
    assert complexity_of("let choose x = try 1 with | :? E -> 2 | _ -> 3\n") == 3
    assert complexity_of("let choose x = try 1 with :? E -> 2 | _ -> 3\n") == 3


def test_given_a_when_guard_on_one_line_when_scoring_then_it_adds_one_and_the_first_arm_nothing():
    assert complexity_of("let choose x = match x with A -> 1 | n when n > 0 -> 2 | _ -> 3\n") == 4


@pytest.mark.parametrize(
    "body",
    [
        "let choose e =\n    match e with\n    | Email v -> v\n",
        "let choose e = match e with Email v -> v\n",
        "let choose = function\n    | Email v -> v\n",
        "let choose xs = List.map (function Email v -> v) xs\n",
        "let choose x =\n    task {\n        match! load x with\n        | Email v -> return v\n    }\n",
    ],
)
def test_given_a_one_arm_unwrap_of_a_single_case_union_when_scoring_then_it_adds_nothing(body):
    assert complexity_of(body) == 1


def test_given_a_when_guard_on_the_only_arm_when_scoring_then_it_adds_one():
    body = """
let choose e =
    match e with
    | Email v when v <> "" -> v
"""
    assert complexity_of(body) == 2


def test_given_a_nested_match_when_scoring_then_it_adds_its_arms_but_the_first():
    body = """
let choose x =
    match x with
    | A ->
        match y with
        | C -> 1
        | D -> 2
    | B -> 3
"""
    assert complexity_of(body) == 3
    assert complexity_of("let choose e = match e with Email v -> (match v with A -> 1 | B -> 2)\n") == 2
    assert complexity_of("let choose e = match e with Email v -> match v with A -> 1 | B -> 2\n") == 2
    assert complexity_of("let choose e = match e with Email v -> (match v with A -> 1 | B | C -> 2)\n") == 2


def test_given_a_match_inside_try_with_when_scoring_then_it_adds_its_arms_but_the_first():
    assert complexity_of("let choose x = try match x with A -> 1 | B -> 2 with _ -> 0\n") == 3
    assert complexity_of("let choose x = try g x with e -> match e with A -> 1 | B -> 2\n") == 3


def test_given_a_comment_before_the_first_arm_when_scoring_then_that_arm_adds_nothing():
    body = """
let choose x =
    match x with
    // the only case
    | Email v -> v
"""
    assert complexity_of(body) == 1


def test_given_an_if_directive_around_the_first_arm_when_scoring_then_that_arm_adds_nothing():
    body = """
let choose x =
    match x with
#if DEBUG
    | A -> 1
#endif
    | B -> 2
"""
    assert complexity_of(body) == 2


_ARM_HEADS = {
    "match": ("let choose x =\n    match x with\n", "let choose x = match x with "),
    "function": ("let choose =\n    function\n", "let choose = function "),
    "try": ("let choose x =\n    try\n        g x\n    with\n", "let choose x = try g x with "),
}


def _every_arm_with_a_bar(kind, arms):
    return _ARM_HEADS[kind][0] + "".join(f"    | {arm}\n" for arm in arms)


def _first_arm_bare(kind, arms):
    return _ARM_HEADS[kind][0] + f"    {arms[0]}\n" + "".join(f"    | {arm}\n" for arm in arms[1:])


def _all_arms_on_one_line(kind, arms):
    return _ARM_HEADS[kind][1] + " | ".join(arms) + "\n"


@pytest.mark.parametrize("layout", [_every_arm_with_a_bar, _first_arm_bare, _all_arms_on_one_line])
@pytest.mark.parametrize(
    ("kind", "arms", "expected"),
    [
        ("match", ["A -> 1", "B | C -> 2"], 2),
        ("match", ["A | B -> 1", "C -> 2"], 2),
        ("match", ["A -> 1", "B | C | D -> 2", "E -> 3"], 3),
        ("match", ["A -> a ||| b", "B -> 2"], 2),
        ("match", ["n when n > 0 -> 1", "_ -> 2"], 3),
        ("match", ["A -> fun y -> y", "B -> fun y -> 0"], 2),
        ("match", ["A -> List.map (fun y -> y + 1) ys", "B | C -> []"], 2),
        ("match", ["(1, _) -> 1, 2", "(_, 2) | (2, _) -> 3, 4", "_ -> 0, 0"], 3),
        ("match", ['A -> "a -> b"', 'B -> "|"'], 2),
        ("match", ["A -> (fun (g: int -> int) -> g)", "B -> id"], 2),
        ("match", ["A -> (id : int -> int)", "B -> id"], 2),
        ("match", ["A -> a --> b", "B -> c"], 2),
        ("match", ["A -> [ for i in xs -> i ]", "B -> []"], 3),
        ("function", ["A -> 1", "B | C -> 2"], 2),
        ("function", ["n when n > 0 -> 1", "_ -> 2"], 3),
        ("function", ["(A, A) -> id", "(A, _) | (_, A) -> fun y -> y", "_ -> id"], 3),
        ("function", ["A -> seq { for i in xs -> i }", "B | C -> Seq.empty"], 3),
        ("try", [":? E -> 2", ":? G | :? H -> 3"], 3),
        ("try", ['Failure m when m = "" -> 1', "_ -> 2"], 4),
        ("try", [":? E -> fun y -> y", "e -> List.map (fun y -> y) ys"], 3),
        ("try", [":? E -> 1, 2", "_ -> 3, 4"], 3),
        ("try", [":? E -> [ for i in xs -> i ]", "_ -> []"], 4),
    ],
)
def test_given_an_arm_list_in_any_layout_when_scoring_then_the_complexity_is_the_same(kind, arms, expected, layout):
    assert complexity_of(layout(kind, arms)) == expected


def test_given_one_line_and_own_line_arms_in_one_match_when_scoring_then_they_mix():
    body = """
let choose x =
    match x with
    | A -> 1 | B | C -> 2
    | D -> 3
"""
    assert complexity_of(body) == 3


@pytest.mark.parametrize(
    ("one_line", "several_lines", "expected"),
    [
        (
            "let choose xs = List.map (fun x -> x + 1) xs\n",
            "let choose xs =\n    List.map\n        (fun x ->\n            x + 1)\n        xs\n",
            1,
        ),
        (
            "let choose = fun x -> fun y -> x + y\n",
            "let choose =\n    fun x ->\n        fun y ->\n            x + y\n",
            1,
        ),
        (
            "let choose (f: int -> int) : int -> int = f >> f\n",
            "let choose (f: int -> int) : int -> int =\n    f >> f\n",
            1,
        ),
        (
            "let choose x = (id : int -> int) x\n",
            "let choose x =\n    (id : int -> int)\n        x\n",
            1,
        ),
        (
            "let choose a b = a --> b >-> a\n",
            "let choose a b =\n    a\n    --> b\n    >-> a\n",
            1,
        ),
        (
            'let choose x = "| A -> 1 | B -> 2" + x // | C -> 3\n',
            'let choose x =\n    "| A -> 1 | B -> 2"\n    + x // | C -> 3\n',
            1,
        ),
    ],
)
def test_given_an_arrow_that_is_no_arm_when_scoring_then_it_adds_nothing(one_line, several_lines, expected):
    assert complexity_of(one_line) == expected
    assert complexity_of(several_lines) == expected


def test_given_an_attribute_on_a_function_name_when_reading_then_it_is_an_entry():
    source = """
module Demo.Program

let [<Literal>] limit = 100
let [<EntryPoint>] main argv = 0
let rec a x = x
and [<Foo>] b y = y
"""
    assert entries(source) == ["main", "a", "b"]


def test_given_a_value_bound_to_an_object_expression_when_reading_then_it_carries_its_members_complexity():
    source = """
module Demo.Resources

let disposable =
    { new System.IDisposable with
        member _.Dispose() = if ready then () else () }

type Holder() =
    let comparer =
        { new System.Collections.Generic.IComparer<int> with
            member _.Compare(a, b) = if a > b then 1 elif a < b then -1 else 0 }
    member _.Comparer = comparer
"""
    found = read(source, "src/Resources.fs")
    assert [(fn.name, fn.complexity) for fn in found] == [
        ("disposable", 2),
        ("comparer", 3),
        ("Comparer", 1),
    ]


def test_given_an_fsharp_project_when_walking_then_build_output_and_test_code_are_skipped(tmp_path, monkeypatch):
    for name in [
        "Demo/src/Board.fs",
        "Demo/src/Testing.fs",
        "Demo/scripts/build.fsx",
        "Demo/src/Board.fsi",
        "Demo/src/obj/Debug/AssemblyInfo.fs",
        "Demo/bin/Release/Gen.fs",
        "Demo/test/Spec.fs",
        "Demo/tests/Unit.fs",
        "Demo.Tests/BoardTests.fs",
        "Demo.Test/BoardTest.fs",
    ]:
        write(tmp_path, name, "")

    def walked(folder: Path) -> list[str]:
        return [path.relative_to(tmp_path.resolve()).as_posix() for path in source_files(folder)]

    assert walked(tmp_path) == ["Demo/scripts/build.fsx", "Demo/src/Board.fs", "Demo/src/Testing.fs"]
    # The walked folder's name is context, never a reason to skip; a named file is its own list.
    assert walked(tmp_path / "Demo" / "test") == ["Demo/test/Spec.fs"]
    assert walked(tmp_path / "Demo.Tests") == ["Demo.Tests/BoardTests.fs"]
    assert walked(tmp_path / "Demo/bin/Release/Gen.fs") == ["Demo/bin/Release/Gen.fs"]
    monkeypatch.chdir(tmp_path / "Demo" / "test")
    assert walked(Path(".")) == ["Demo/test/Spec.fs"]


@pytest.mark.parametrize("outer", ["test", "bin", "obj"])
def test_given_a_project_inside_a_skipped_folder_name_when_walking_then_its_fsharp_files_are_kept(tmp_path, outer):
    root = tmp_path / outer / "Demo"
    for name in ("src/Board.fs", "test/Spec.fs", "src/obj/Gen.fs", "bin/Tool.fs"):
        write(root, name, "module Demo\nlet f x = x\n")
    assert source_files(root) == [(root / "src/Board.fs").resolve()]
