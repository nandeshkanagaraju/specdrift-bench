"""Split Python sources into retrievable chunks using the ast module.

One chunk per module-level function, per method (qualname ``Class.method``), one per
class header (the decorator/signature plus any class-level attributes), and one
``<module>`` chunk holding the top-level statements - imports and the named constants
that rules like "the loan period MUST be 14 days" are written against. Line spans carry
the full original source, comments included, because a comment that lies about the code
is itself a drift signal.
"""

from __future__ import annotations

import ast
from pathlib import Path

from specdrift.bench.schema import Chunk


def _segment(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])


def _node_start(node: ast.AST) -> int:
    """First line of a definition, counting its decorators."""
    decorators = getattr(node, "decorator_list", [])
    starts = [node.lineno] + [d.lineno for d in decorators]
    return min(starts)


def chunk_source(source: str, rel_path: str) -> list[Chunk]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    chunks: list[Chunk] = []

    def add(qualname: str, start: int, end: int) -> None:
        if end < start:
            return
        chunks.append(
            Chunk(
                id=f"{rel_path}::{qualname}",
                file=rel_path,
                qualname=qualname,
                start_line=start,
                end_line=end,
                source=_segment(lines, start, end),
            )
        )

    # The module chunk: every top-level statement that is not a def or a class, which
    # is where module constants live. Without it a constant drift is unretrievable.
    module_stmts = [
        node
        for node in tree.body
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if module_stmts:
        body = "\n".join(
            _segment(lines, _node_start(node), node.end_lineno or node.lineno)
            for node in module_stmts
        )
        chunks.append(
            Chunk(
                id=f"{rel_path}::<module>",
                file=rel_path,
                qualname="<module>",
                start_line=_node_start(module_stmts[0]),
                end_line=module_stmts[-1].end_lineno or module_stmts[-1].lineno,
                source=body,
            )
        )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node.name, _node_start(node), node.end_lineno or node.lineno)

        elif isinstance(node, ast.ClassDef):
            methods = [
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            # Class header: everything from the decorators down to the first method,
            # which is where docstrings and class-level constants live.
            header_end = (
                _node_start(methods[0]) - 1
                if methods
                else (node.end_lineno or node.lineno)
            )
            add(node.name, _node_start(node), header_end)

            for method in methods:
                add(
                    f"{node.name}.{method.name}",
                    _node_start(method),
                    method.end_lineno or method.lineno,
                )

    return chunks


def chunk_file(path: str | Path, root: str | Path) -> list[Chunk]:
    path, root = Path(path), Path(root)
    rel = path.relative_to(root).as_posix()
    return chunk_source(path.read_text(encoding="utf-8"), rel)


def chunk_workspace(root: str | Path, subdir: str = "src") -> list[Chunk]:
    """Chunk every .py file under ``root/subdir`` (or under root if subdir is absent)."""
    root = Path(root)
    base = root / subdir
    if not base.exists():
        base = root

    chunks: list[Chunk] = []
    for py in sorted(base.rglob("*.py")):
        if any(part in {"__pycache__", ".venv", ".pytest_cache"} for part in py.parts):
            continue
        chunks.extend(chunk_file(py, root))

    chunks.sort(key=lambda c: c.id)
    return chunks
