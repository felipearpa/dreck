# Adapted from doppel's src/doppel/treesitter.py, adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/treesitter.py (0BSD), with `complexity` from crapper's src/crapper/languages/treesitter.py (0BSD).
from functools import lru_cache


@lru_cache(maxsize=None)
def parser_for(language: str):
    from tree_sitter_language_pack import download, get_parser

    download([language])
    return get_parser(language)


def parse(source: str, language: str):
    data = source.encode("utf-8")
    tree = parser_for(language).parse(data)
    return data, tree


def node_text(data: bytes, node) -> str:
    return data[node.start_byte : node.end_byte].decode("utf-8")


def start_line(node) -> int:
    return node.start_point[0] + 1


def end_line(node) -> int:
    row, col = node.end_point
    if col == 0:
        return max(start_line(node), row)
    return row + 1


def child_of_type(node, *types: str):
    for child in node.children:
        if child.type in types:
            return child
    return None


def complexity(node, is_decision) -> int:
    """McCabe complexity of `node`: 1 plus each decision in the subtree.

    The walk is a stack, not recursion. A generated expression can be deeper
    than Python's call limit.
    """

    total = 1
    stack = [node]
    while stack:
        current = stack.pop()
        if is_decision(current):
            total += 1
        stack.extend(reversed(current.children))
    return total
