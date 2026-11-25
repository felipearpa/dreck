# Reader adapted from crapper's src/crapper/languages/fsharp.py (0BSD), without its namespace; skip rules written from crapper's src/crapper/discover.py.
"""Everything dreck knows about F#.

Decision points are `if`, `elif`, `for` (also its short form, `for ... ->`),
`while`, each arm of `match`, `match!`, and `function` except the first, each
handler of `try ... with` (arms and handlers alike on one line or several; on
one line a later arm is found by its `->`, so an or-pattern adds nothing),
each `when` guard on an arm, and each `&&` / `||`. A `match` is assumed to
cover its type, so one the compiler flags with FS0025 counts one path too few.
Combinator calls such as `Option.map` and computation-expression binds such as
`let!` add nothing.

Entries are module- and type-level `let` functions, members, active patterns
(named by their pattern text, `|Even|Odd|`), and lambdas bound to a value
(`let handler = fun ...` or `= function ...`), and values bound to an object
expression, which carry the complexity of its members. A function, lambda, or
object expression inside another entry stays in that entry. Other values, such
as a partial application or a composition, are not entries.

Node names are those of the F# grammar shipped in tree-sitter-language-pack
1.25.2.
"""

from pathlib import PurePosixPath

from dreck.coverage import BY_FILE_LINES
from dreck.model import Function
from dreck.spec import LanguageSpec
from dreck.treesitter import child_of_type, complexity, end_line, node_text, parse, start_line

_DECISIONS = {
    "if_expression",
    "elif_expression",
    "for_expression",
    "short_comp_expression",
    "while_expression",
}
_LOGIC = {"&&", "||"}
_COMPLETE_MATCHES = {"match_expression", "function_expression"}
_BODIES = {"function_or_value_defn", "method_or_prop_defn"}
_LAMBDAS = {"fun_expression", "function_expression"}
_NAME_NODES = ("identifier", "active_pattern", "op_identifier")


def _is_guard(data: bytes, node) -> bool:
    if node.type == "when":
        return node.parent is not None and node.parent.type == "rule"
    # On one line, the grammar reads arms after the first as infix
    # expressions, so their `when` arrives as an identifier. `when` is a
    # keyword and cannot name anything else.
    return node.type == "identifier" and node_text(data, node) == "when"


def _is_counted_arm(node) -> bool:
    # A `match` is assumed to cover its type, so with n arms it has n paths
    # and adds n - 1. A handler always adds one: the body can finish without one.
    if node.type != "rule":
        return False
    rules = node.parent
    owner = rules.parent if rules is not None else None
    if owner is None or owner.type not in _COMPLETE_MATCHES:
        return True
    return child_of_type(rules, "rule") != node


def _is_one_line_arm(data: bytes, node) -> bool:
    # The grammar reads a later arm on one line as an infix in the first arm's
    # body. Its `|` may join an or-pattern, but its `->` is one per arm and no
    # F# operator; a lambda's or a type's arrow is never an infix_op.
    return node.type == "infix_op" and node_text(data, node) == "->"


def _is_logic(data: bytes, node) -> bool:
    if node.type != "infix_expression":
        return False
    op = child_of_type(node, "infix_op")
    return op is not None and node_text(data, op) in _LOGIC


def _decision_test(data: bytes):
    def is_decision(node) -> bool:
        return (
            node.type in _DECISIONS
            or _is_counted_arm(node)
            or _is_one_line_arm(data, node)
            or _is_guard(data, node)
            or _is_logic(data, node)
        )

    return is_decision


def _is_nested(node) -> bool:
    current = node.parent
    while current is not None:
        if current.type in _BODIES:
            return True
        current = current.parent
    return False


def _unwrap(node):
    """The expression inside parentheses and type annotations."""

    current = node
    while current is not None and current.type in {"paren_expression", "typecast_expression"}:
        current = next((child for child in current.children if child.is_named), None)
    return current


def _pattern_name(data: bytes, node) -> str:
    text = "".join(node_text(data, node).split())
    if text.startswith("(") and text.endswith(")"):
        return text[1:-1]
    return text


def _named_function(data: bytes, name) -> str | None:
    """The name of a `let` with arguments, or None for a union case pattern.

    The grammar reads `let Some y = opt` as a function named `Some`. F# names
    `let` functions in camelCase, so an uppercase name is a union case.
    """

    text = node_text(data, name)
    return None if text.split(".")[-1][:1].isupper() else text


def _function_name(data: bytes, left) -> str | None:
    name = child_of_type(left, *_NAME_NODES)
    if name is None:
        return None
    if name.type == "identifier":
        return _named_function(data, name)
    return _pattern_name(data, name)


def _name_pattern(left):
    pattern = child_of_type(left, "identifier_pattern", "attribute_pattern")
    if pattern is not None and pattern.type == "attribute_pattern":
        return child_of_type(pattern, "identifier_pattern")
    return pattern


def _is_entry_value(value) -> bool:
    """A lambda, or an object expression whose members carry the logic."""

    if value is None:
        return False
    if value.type == "brace_expression":
        return child_of_type(value, "object_expression") is not None
    return value.type in _LAMBDAS


def _value_name(data: bytes, left, body) -> str | None:
    pattern = _name_pattern(left)
    if pattern is None:
        return None
    # The grammar reads some functions with a return type, `let f x : T =`,
    # as a value whose pattern is the name followed by its arguments.
    if pattern.named_child_count > 1:
        return _named_function(data, pattern.named_children[0])
    if not _is_entry_value(_unwrap(body)):
        return None
    return node_text(data, pattern)


def _binding_name(data: bytes, left, body) -> str | None:
    if left.type == "function_declaration_left":
        return _function_name(data, left)
    return _value_name(data, left, body)


def _bindings(defn):
    """(start node, left, body) for each binding of `let` / `let rec ... and`."""

    start = defn
    left = None
    for index, child in enumerate(defn.children):
        if child.type == "and":
            start = child
        elif child.type in {"function_declaration_left", "value_declaration_left"}:
            left = child
        elif left is not None and defn.field_name_for_child(index) == "body":
            yield start, left, child
            left = None


def _member_name(data: bytes, defn) -> str | None:
    name = child_of_type(defn, "property_or_ident")
    if name is None:
        return None
    ident = name.child_by_field_name("method") or child_of_type(name, "identifier")
    return node_text(data, ident) if ident is not None else None


class _Reader:
    def __init__(self, data: bytes, path: str):
        self.data = data
        self.path = path
        self.is_decision = _decision_test(data)
        self.found: list[Function] = []

    def add(self, name: str, first, last, body) -> None:
        self.found.append(
            Function(
                name=name,
                complexity=complexity(body, self.is_decision),
                start_line=start_line(first),
                end_line=end_line(last),
                path=self.path,
            )
        )

    def read_let(self, defn) -> None:
        for start, left, body in _bindings(defn):
            name = _binding_name(self.data, left, body)
            if name is not None:
                self.add(name, start, body, body)

    def read_member(self, defn) -> None:
        name = _member_name(self.data, defn)
        if name is None:
            return
        owner = defn.parent if defn.parent is not None else defn
        self.add(name, owner, defn, defn)

    def read(self, node) -> None:
        if node.type not in _BODIES or _is_nested(node):
            return
        if node.type == "function_or_value_defn":
            self.read_let(node)
        else:
            self.read_member(node)


def _functions(source: str, path: str) -> tuple[list[Function], bool]:
    data, tree = parse(source, "fsharp")
    reader = _Reader(data, path)
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        reader.read(node)
        stack.extend(reversed(node.children))
    return reader.found, tree.root_node.has_error


# .NET build output, and test projects and folders.
_BUILD = frozenset({"bin", "obj"})
_TESTS = frozenset({"test", "tests"})
_TEST_ENDINGS = (".Test", ".Tests")


def _skips(path: PurePosixPath) -> bool:
    """Build output and test code, at any depth.

    The first part is the walked folder's name: context only.
    """

    return any(part in _BUILD or part in _TESTS or part.endswith(_TEST_ENDINGS) for part in path.parts[1:])


SPEC = LanguageSpec(
    name="F#",
    extensions=frozenset({".fs", ".fsx"}),
    skips=_skips,
    functions=_functions,
    reports="the Cobertura reports of dotnet test",
    lookup=BY_FILE_LINES,
    prunes=_BUILD,
)
