# Reader adapted from crapper's src/crapper/languages/kotlin.py (0BSD); skip rules copied from doppel's src/doppel/languages/kotlin.py.
"""Everything dreck knows about Kotlin.

Decision points are `if`, `for`, `while`, `do ... while`, each `when` arm
except `else`, each `catch`, and each `&&`, `||`, `?:`, and `?.`.

Functions are those with a body that are not inside another function, a
lambda, or an anonymous object; those stay in the enclosing function.
Constructors, `init` blocks, property accessors, and abstract functions are
not read. The JVM class (`pkg.Outer$Inner`, `pkg.Enum$VALUE`, or `pkg.FileKt`
and `@file:JvmName` for top-level functions) is kept for coverage lookup.

Node names are those of the fwcd/tree-sitter-kotlin grammar shipped in
tree-sitter-language-pack 1.25.2.
"""

import re
from pathlib import PurePosixPath

from dreck.coverage import BY_JVM_CLASS
from dreck.model import Function
from dreck.spec import LanguageSpec
from dreck.treesitter import child_of_type, complexity, end_line, node_text, parse, start_line

_JVM_NAME = re.compile(r'(?m)^\s*@file:JvmName\("([^"]+)"\)')
# `@Composable () -> Unit`: an annotation without arguments, a space, then a
# parenthesis. The grammar reads the parenthesis as the annotation's arguments
# and loses the rest of the file.
_TYPE_ANNOTATION = re.compile(r"@[A-Za-z_][\w.]*(?=[ \t]+\()", re.ASCII)
_TYPES = {"class_declaration", "object_declaration", "companion_object", "enum_entry"}
_NESTING = {"lambda_literal", "object_literal", "anonymous_function"}
_DECISIONS = {
    "if_expression",
    "for_statement",
    "while_statement",
    "do_while_statement",
    "catch_block",
    "&&",
    "||",
    "?:",
    "?.",
}


def _blank_annotations(source: str) -> str:
    """Every byte and line stays in place, so line numbers still match the file."""

    return _TYPE_ANNOTATION.sub(lambda found: " " * len(found.group(0)), source)


def _is_decision(node) -> bool:
    if node.type == "when_entry":
        return child_of_type(node, "else") is None
    return node.type in _DECISIONS


def _type_name(data: bytes, node) -> str | None:
    if node.type == "enum_entry":
        if child_of_type(node, "class_body") is None:
            return None
        return node_text(data, child_of_type(node, "simple_identifier"))
    ident = child_of_type(node, "type_identifier")
    if ident is not None:
        return node_text(data, ident)
    return "Companion" if node.type == "companion_object" else None


def _type_chain(data: bytes, node) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type in _TYPES:
            name = _type_name(data, current)
            if name:
                names.append(name)
        current = current.parent
    names.reverse()
    return names


def _package(data: bytes, root) -> str | None:
    header = child_of_type(root, "package_header")
    ident = child_of_type(header, "identifier") if header is not None else None
    return node_text(data, ident) if ident is not None else None


def _facade(source: str, path: str) -> str:
    """The JVM class that holds a file's top-level functions."""

    found = _JVM_NAME.search(source)
    if found:
        return found.group(1)
    stem = PurePosixPath(path).stem
    return stem[:1].upper() + stem[1:] + "Kt"


class _Reader:
    def __init__(self, data: bytes, source: str, path: str, package: str | None):
        self.data = data
        self.path = path
        self.package = package
        self.facade = _facade(source, path)
        self.found: list[Function] = []

    def _jvm_class(self, chain: list[str]) -> str:
        return ".".join(part for part in (self.package, "$".join(chain or [self.facade])) if part)

    def read(self, node) -> None:
        ident = child_of_type(node, "simple_identifier")
        if ident is None or child_of_type(node, "function_body") is None:
            return
        self.found.append(
            Function(
                name=node_text(self.data, ident),
                complexity=complexity(node, _is_decision),
                start_line=start_line(node),
                end_line=end_line(node),
                path=self.path,
                jvm_class=self._jvm_class(_type_chain(self.data, node)),
            )
        )


def _functions(source: str, path: str) -> tuple[list[Function], bool]:
    data, tree = parse(_blank_annotations(source), "kotlin")
    reader = _Reader(data, source, path, _package(data, tree.root_node))
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "function_declaration":
            reader.read(node)
            continue
        if node.type in _NESTING:
            continue
        stack.extend(reversed(node.children))
    return reader.found, tree.root_node.has_error


_BUILD = frozenset({"build", ".gradle"})
_TEST_ENDINGS = ("Test.kt", "Tests.kt", "Spec.kt")


def _skips(path: PurePosixPath) -> bool:
    """Build output, test source sets and test files.

    A test source set is a folder right under `src` whose name contains
    "test": `test`, `androidTest`, `commonTest`, `testFixtures`.
    """

    parts = path.parts
    below = parts[1:]
    # Build output sits beside `src`; a package called `build` inside it is code.
    # The first part, the walked folder's name, counts as a `src` parent, never as a `build`.
    above_src = parts[1 : parts.index("src")] if "src" in parts else below
    if _BUILD.intersection(above_src) or (below and below[-1].endswith(_TEST_ENDINGS)):
        return True
    return any(
        parent == "src" and "test" in child.lower() and not child.endswith(".kt")
        for parent, child in zip(parts, parts[1:])
    )


SPEC = LanguageSpec(
    name="Kotlin",
    extensions=frozenset({".kt"}),
    skips=_skips,
    functions=_functions,
    reports="Kover's XML report",
    lookup=BY_JVM_CLASS,
    # `build` is left out: a package folder called `build` inside `src/` is code.
    prunes=frozenset({".gradle"}),
)
