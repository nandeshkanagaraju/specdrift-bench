"""N2 and N3: code changes that must NOT be flagged as drift (docs/training-data-spec.md, section 6).

N2  semantics-preserving refactors: the code is rewritten and behaves the same.
N3  benign decoys: something alarming is added (a comment, a docstring caveat, a dead branch) next to code
    that still does exactly what the rule says.

These are the examples a detector over-flags, so they are the hard negatives: the benchmark's SpecGuard flags
63 percent of its controls, two thirds of the refactors among them.

Nothing here is trusted to preserve behaviour. A candidate becomes a COMPLIANT example only if the project's own
suite *and* every oracle for the rules covering the changed code still pass (see `assemble.py`).

Two safeguards against test-set leakage. First, the wording of the N3 text is checked against every string in
`cases/*.yaml` by a test. Second, each N2 operator records whether its *family* also appears in the benchmark
(`OVERLAPS_BENCHMARK`), so the mixer can exclude those families and a held-out-family result can be reported.
"""

from __future__ import annotations

import ast

from specdrift.data.candidate import Candidate

# Operators whose family the benchmark's own N2 cases also use (library/ratelimiter/wallet N2-01..06).
OVERLAPS_BENCHMARK = {
    "rename_local": True,          # library-N2-04, ratelimiter-N2-02, wallet-N2-04
    "swap_compare_sides": False,
    "not_eq": False,
    "expand_augassign": False,
    "extract_temp": True,          # wallet-N2-06 extracts a tuple key into a local
    "reorder_assignments": False,
    "decoy_comment": True,         # the N3 family: an alarming comment
    "decoy_docstring": True,       # the N3 family: an alarming docstring
    "decoy_dead_branch": False,
}

# Deliberately different wording from the benchmark's own decoys ("no longer enforced", "advisory only",
# "no-op", "currently disabled", "not applied in this build"); tests/test_benign.py checks this against cases/*.yaml.
COMMENTS = (
    "HACK: the usual guard is skipped on this path until the rewrite lands",
    "FIXME: this limit looks wrong, confirm with the team before shipping",
    "legacy path, kept only until the migration finishes",
    "WARNING: validation was relaxed here for the beta",
    "XXX: behaviour here differs from the written spec, see the open ticket",
    "temporary: the upper bound is waived on this branch",
    "reviewer: is this check even reachable any more?",
    "left over from the old design, safe to delete",
)
CAVEATS = (
    "Caveat: the bound is waived on the fast path.",
    "Caveat: callers are trusted, so nothing is verified here.",
    "Caveat: written for the old schema; some rules may not hold.",
    "Caveat: limits are applied by the caller, not here.",
)
DEAD_BRANCH_NOTES = (
    "old limit check, switched off",
    "validation removed for the beta",
    "limit handled elsewhere now",
)

_SUFFIXES = ("_value", "_item", "_local", "_tmp", "_x")


# --------------------------------------------------------------------------- N2


def _functions(tree: ast.AST) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _simple(node: ast.AST) -> bool:
    """An operand whose evaluation has no side effect and does not depend on order."""
    if isinstance(node, (ast.Name, ast.Constant)):
        return True
    if isinstance(node, ast.Attribute):
        return _simple(node.value)
    if isinstance(node, ast.Subscript):
        return _simple(node.value) and _simple(node.slice)
    return False


def _one_line(node: ast.AST, line: str) -> bool:
    return (getattr(node, "lineno", 0) == getattr(node, "end_lineno", -1) and line.isascii()
            and getattr(node, "end_col_offset", None) is not None)


def rename_local(source: str) -> list[Candidate]:
    lines = source.splitlines()
    found: list[Candidate] = []
    for fn in _functions(ast.parse(source)):
        params = {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs, *fn.args.posonlyargs]}
        params |= {a.arg for a in (fn.args.vararg, fn.args.kwarg) if a}
        body = [n for stmt in fn.body for n in ast.walk(stmt)]
        if any(isinstance(n, (ast.JoinedStr, ast.Global, ast.Nonlocal, ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.ClassDef))
               for n in body):
            continue
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("locals", "vars", "eval", "exec")
               for n in body):
            continue
        stored = {n.id for n in body if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)} - params
        everything = _names_in(ast.Module(body=[fn], type_ignores=[])) | set(dir(__builtins__))
        for old in sorted(stored):
            uses = [n for n in body if isinstance(n, ast.Name) and n.id == old]
            if len(uses) < 2 or any(not _one_line(n, lines[n.lineno - 1]) for n in uses):
                continue
            new = next((old + s for s in _SUFFIXES if old + s not in everything), None)
            if new is None:
                continue
            first, last = min(n.lineno for n in uses), max(n.lineno for n in uses)
            new_lines = list(lines[first - 1: last])
            for n in sorted(uses, key=lambda x: (x.lineno, -x.col_offset)):
                row = n.lineno - first
                text = new_lines[row]
                new_lines[row] = text[: n.col_offset] + new + text[n.end_col_offset:]
            found.append(Candidate("N2", "rename_local", first, last, new_lines, f"local `{old}` is renamed `{new}`"))
    return found


def swap_compare_sides(source: str) -> list[Candidate]:
    lines = source.splitlines()
    flip = {ast.Lt: ">", ast.Gt: "<", ast.LtE: ">=", ast.GtE: "<=", ast.Eq: "==", ast.NotEq: "!="}
    found: list[Candidate] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in flip):
            continue
        text = lines[node.lineno - 1]
        left, right = node.left, node.comparators[0]
        if not (_one_line(node, text) and _simple(left) and _simple(right)):
            continue
        a, b = text[left.col_offset: left.end_col_offset], text[right.col_offset: right.end_col_offset]
        if a == b:
            continue
        changed = text[: node.col_offset] + f"{b} {flip[type(node.ops[0])]} {a}" + text[node.end_col_offset:]
        found.append(Candidate("N2", "swap_compare_sides", node.lineno, node.lineno, [changed],
                               f"`{a} ? {b}` is written the other way round"))
    return found


def not_eq(source: str) -> list[Candidate]:
    lines = source.splitlines()
    found: list[Candidate] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.NotEq):
            text = lines[node.lineno - 1]
            left, right = node.left, node.comparators[0]
            if _one_line(node, text) and _simple(left) and _simple(right):
                a, b = text[left.col_offset: left.end_col_offset], text[right.col_offset: right.end_col_offset]
                changed = text[: node.col_offset] + f"not ({a} == {b})" + text[node.end_col_offset:]
                found.append(Candidate("N2", "not_eq", node.lineno, node.lineno, [changed], f"`{a} != {b}` becomes `not ({a} == {b})`"))
    return found


def expand_augassign(source: str) -> list[Candidate]:
    lines = source.splitlines()
    ops = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}
    found: list[Candidate] = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.AugAssign) and type(node.op) in ops and isinstance(node.target, ast.Name)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float))
                and not isinstance(node.value.value, bool)):
            text = lines[node.lineno - 1]
            if _one_line(node, text):
                name, value = node.target.id, text[node.value.col_offset: node.value.end_col_offset]
                changed = text[: node.col_offset] + f"{name} = {name} {ops[type(node.op)]} {value}" + text[node.end_col_offset:]
                found.append(Candidate("N2", "expand_augassign", node.lineno, node.lineno, [changed],
                                       f"`{name} {ops[type(node.op)]}= {value}` is written out in full"))
    return found


def extract_temp(source: str) -> list[Candidate]:
    lines = source.splitlines()
    found: list[Candidate] = []
    for fn in _functions(ast.parse(source)):
        used = _names_in(ast.Module(body=[fn], type_ignores=[]))
        name = next((n for n in ("result_", "out_", "value_") if n not in used), None)
        if name is None:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Return) and node.value is not None and isinstance(
                    node.value, (ast.Call, ast.BinOp, ast.Compare, ast.BoolOp)):
                text = lines[node.lineno - 1]
                if _one_line(node, text) and _one_line(node.value, text):
                    indent = text[: node.col_offset]
                    expr = text[node.value.col_offset: node.value.end_col_offset]
                    found.append(Candidate("N2", "extract_temp", node.lineno, node.lineno,
                                           [f"{indent}{name} = {expr}", f"{indent}return {name}"],
                                           f"the returned value is kept in `{name}` first"))
    return found


def reorder_assignments(source: str) -> list[Candidate]:
    lines = source.splitlines()
    found: list[Candidate] = []
    for node in ast.walk(ast.parse(source)):
        for block in (getattr(node, f, None) for f in ("body", "orelse", "finalbody")):
            if not isinstance(block, list):
                continue
            for first, second in zip(block, block[1:], strict=False):
                if not (isinstance(first, ast.Assign) and isinstance(second, ast.Assign)):
                    continue
                if not (first.lineno == first.end_lineno and second.lineno == second.end_lineno
                        and second.lineno == first.lineno + 1):
                    continue
                pure = all(isinstance(s.value, (ast.Constant, ast.Name)) and len(s.targets) == 1
                           and isinstance(s.targets[0], ast.Name) for s in (first, second))
                if not pure:
                    continue
                t1, t2 = first.targets[0].id, second.targets[0].id  # type: ignore[attr-defined]
                if t1 == t2 or t1 in _names_in(second.value) or t2 in _names_in(first.value):
                    continue
                found.append(Candidate("N2", "reorder_assignments", first.lineno, second.lineno,
                                       [lines[second.lineno - 1], lines[first.lineno - 1]],
                                       f"the independent assignments to `{t1}` and `{t2}` swap places"))
    return found


# --------------------------------------------------------------------------- N3


def _statement_starts(tree: ast.AST) -> list[ast.stmt]:
    stmts: list[ast.stmt] = []
    for fn in _functions(tree):
        for stmt in ast.walk(fn):
            if isinstance(stmt, (ast.If, ast.Return, ast.Raise, ast.Assign, ast.AugAssign, ast.Expr, ast.For, ast.While)):
                if stmt is not fn.body[0] or not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)):
                    stmts.append(stmt)
    return stmts


def decoy_comment(source: str) -> list[Candidate]:
    lines = source.splitlines()
    found: list[Candidate] = []
    for stmt in _statement_starts(ast.parse(source)):
        row = stmt.lineno
        text = lines[row - 1]
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue                                              # a docstring or stray string, not a statement to annotate
        note = COMMENTS[(row * 7 + len(text)) % len(COMMENTS)]
        indent = text[: len(text) - len(text.lstrip())]
        found.append(Candidate("N3", "decoy_comment", row, row, [f"{indent}# {note}", text], f"a comment says: {note}"))
    return found


def decoy_docstring(source: str) -> list[Candidate]:
    lines = source.splitlines()
    found: list[Candidate] = []
    for fn in _functions(ast.parse(source)):
        first = fn.body[0]
        if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)):
            continue
        text = lines[first.lineno - 1]
        if not text.rstrip().endswith('"""') or text.count('"""') != 2:        # a one-line docstring only
            continue
        caveat = CAVEATS[(first.lineno * 5 + len(text)) % len(CAVEATS)]
        body = text.rstrip()
        changed = body[:-3].rstrip() + " " + caveat + '"""'
        found.append(Candidate("N3", "decoy_docstring", first.lineno, first.lineno, [changed], f"the docstring adds: {caveat}"))
    return found


def decoy_dead_branch(source: str) -> list[Candidate]:
    lines = source.splitlines()
    found: list[Candidate] = []
    for stmt in _statement_starts(ast.parse(source)):
        if isinstance(stmt, (ast.If, ast.Raise)):
            row = stmt.lineno
            text = lines[row - 1]
            if text.lstrip().startswith(("elif ", "else")):
                continue                    # `if False: pass` before an `elif` would re-attach it and rewire the chain
            indent = text[: len(text) - len(text.lstrip())]
            note = DEAD_BRANCH_NOTES[(row * 3 + len(text)) % len(DEAD_BRANCH_NOTES)]
            found.append(Candidate("N3", "decoy_dead_branch", row, row,
                                   [f"{indent}if False:  # {note}", f"{indent}    pass", text],
                                   f"an unreachable branch is added: {note}"))
    return found


# --------------------------------------------------------------------------- entry point


def benign_candidates(source: str) -> list[Candidate]:
    out: list[Candidate] = []
    for generator in (rename_local, swap_compare_sides, not_eq, expand_augassign, extract_temp, reorder_assignments,
                      decoy_comment, decoy_docstring, decoy_dead_branch):
        out += generator(source)
    return out
