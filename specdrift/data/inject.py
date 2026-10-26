"""Stage B, part 1: inject drift into a Python project and label each mutant by running its tests.

Operators map onto the benchmark's categories (docs/training-data-spec.md, section 5):

    D1  boundary shift        < <-> <=, > <-> >=, an integer slice bound moves by one
    D2  value / constant      a number or string becomes a different one, + <-> -, a boolean argument flips
    D3  omitted check / step  an `if ...: raise` guard, or a simple statement, is deleted (or becomes `pass`);
                              the `key=` of a sort is removed
    D4  weakened condition    and <-> or, == <-> !=, `not x` -> `x`, is <-> is not, in <-> not in, `if x` -> `if not (x)`
    D5  sequence violation    two adjacent statements swap places, or a call's first two arguments do
    D6  error-handling drift  `raise X` raises a different exception class
    D9  output contract       return True <-> False, `return <expression>` -> `return None`

D7 (comment decoy) and D8 (scope creep) cannot be checked by running a test, so they are written
and reviewed by hand, not generated here.

Every mutant is a find/replace patch that matches its file exactly once, the same format as
cases/*.yaml, so it records as `inject_find` / `inject_replace` for the leakage check. A mutant is
labelled by what the project's own suite does with it:

    killed    the suite fails on an assertion: observable behaviour changed (a DRIFT candidate)
    survived  the suite still passes: unverified, needs an oracle test before it may be called DRIFT
    preserved an N2 refactor or N3 decoy (`--benign`) whose suite still passes, as it must; if the suite
              fails the change was not behaviour-preserving, and it is recorded as `killed` and not used
    crash     the suite fails only because the code no longer loads or names something that is gone
    timeout   the suite hung; the mutant is unreliable and is not used
    invalid   the patched file does not compile

Third-party tests are run with the network off and writes confined to scratch space, using
`sandbox-exec` where it exists.
"""

from __future__ import annotations

import ast
import io
import json
import keyword
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from specdrift.bench.builder import IGNORED, PatchError, apply_patch
from specdrift.code.chunker import chunk_source
from specdrift.data.benign import benign_candidates
from specdrift.data.candidate import Candidate

Status = Literal["killed", "survived", "preserved", "crash", "timeout", "invalid"]
SandboxMode = Literal["auto", "require", "off"]

CATEGORIES = ("D1", "D2", "D3", "D4", "D5", "D6", "D9")
CONTEXT_LINES = 3          # most surrounding lines added to make a patch unique
CRASH_ERRORS = ("NameError", "UnboundLocalError", "SyntaxError", "IndentationError", "ImportError",
                "ModuleNotFoundError")

_BOUNDARY = {"<": "<=", "<=": "<", ">": ">=", ">=": ">"}
# A parametrized test id may contain spaces ("test_tokenize[assignment in value]"), so the id runs up to the first
# " - " (or the end of the line) and not to the first space. A path with no "::" falls back to the old form.
# pytest 9 reports a failing subtest (unittest `self.subTest`, or the `subtests` fixture) as
# "SUBFAILED[case 2] (n=2) path::Class::test - message" and the parent test itself passes, so there is no
# FAILED line at all; the bracketed description and the parenthesised parameters are skipped.
_FAILED_RE = re.compile(
    r"^(?:FAILED|SUBFAILED(?:\[.*?\])?(?:\s*\(.*?\))?)\s+(?P<test>\S+::.+?|\S+)(?:\s+-\s+(?P<message>.*))?$",
    re.MULTILINE,
)


class Mutant(BaseModel):
    mutant_id: str
    project: str
    category: str
    operator: str
    file: str                     # relative to the project root
    line: int                     # first changed line, 1-based
    symbol: str                   # enclosing chunk, as the chunker names it
    find: str
    replace: str
    description: str
    status: Status
    failing_test: str = ""
    failure_message: str = ""
    sandboxed: bool = False


class ProjectBroken(RuntimeError):
    """The unmodified project does not pass its own tests, so no mutant can be labelled."""




# --------------------------------------------------------------------------- candidates


def _tokens(source: str) -> list[tokenize.TokenInfo]:
    return list(tokenize.generate_tokens(io.StringIO(source).readline))


def _splice(line: str, start: int, end: int, text: str) -> str:
    return line[:start] + text + line[end:]


def _bumped(text: str) -> str | None:
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value + 1)
    if isinstance(value, float):
        return repr(round(value * 1.5 if value else 1.0, 6))
    return None


def token_candidates(source: str) -> list[Candidate]:
    lines = source.splitlines()
    toks = [t for t in _tokens(source) if t.type not in (tokenize.NL, tokenize.COMMENT)]
    found: list[Candidate] = []

    def edit(tok: tokenize.TokenInfo, new: str, category: str, operator: str, why: str) -> None:
        row = tok.start[0]
        changed = _splice(lines[row - 1], tok.start[1], tok.end[1], new)
        found.append(Candidate(category, operator, row, row, [changed], why))

    for i, tok in enumerate(toks):
        prev = toks[i - 1] if i else None
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if tok.type == tokenize.OP and tok.string in _BOUNDARY:
            edit(tok, _BOUNDARY[tok.string], "D1", "boundary", f"`{tok.string}` becomes `{_BOUNDARY[tok.string]}`")
        elif tok.type == tokenize.NAME and tok.string in ("and", "or"):
            other = "or" if tok.string == "and" else "and"
            edit(tok, other, "D4", "and_or", f"`{tok.string}` becomes `{other}`")
        elif tok.type == tokenize.OP and tok.string in ("==", "!="):
            other = "!=" if tok.string == "==" else "=="
            edit(tok, other, "D4", "invert_eq", f"`{tok.string}` becomes `{other}`")
        elif tok.type == tokenize.NUMBER:
            if prev and prev.string == "[" or nxt and nxt.string == "]":
                continue                              # an index change mostly just crashes
            new = _bumped(tok.string)
            if new is not None:
                edit(tok, new, "D2", "constant", f"constant {tok.string} becomes {new}")
        elif tok.type == tokenize.NAME and prev and prev.string == "raise" and tok.string[:1].isupper():
            new = "RuntimeError" if tok.string == "ValueError" else "ValueError"
            if new != tok.string:
                edit(tok, new, "D6", "exception_type", f"raises {new} instead of {tok.string}")
        elif tok.type == tokenize.NAME and prev and prev.string == "return":
            if tok.string in ("True", "False"):
                new = "False" if tok.string == "True" else "True"
                edit(tok, new, "D9", "flip_bool", f"returns {new} instead of {tok.string}")
            elif tok.string.isidentifier() and tok.string != "None" and nxt and nxt.type == tokenize.NEWLINE:
                edit(tok, "None", "D9", "return_none", f"returns None instead of {tok.string}")

        # Operators added after the pilot showed 22 of 57 cited lines were out of reach (section 11 of the design doc).
        row = tok.start[0]

        def span(start: int, end: int, new: str, operator: str, why: str, category: str = "D4", _row: int = row) -> None:
            found.append(Candidate(category, operator, _row, _row, [_splice(lines[_row - 1], start, end, new)], why))

        same_row = nxt is not None and nxt.start[0] == row
        if tok.type == tokenize.NAME and tok.string == "not" and same_row and nxt is not None:
            if nxt.string == "in" and not (prev and prev.string == "is"):
                span(tok.start[1], nxt.start[1], "", "flip_in", "`not in` becomes `in`")
            elif not (prev and prev.string == "is"):
                span(tok.start[1], nxt.start[1], "", "drop_not", "`not` is removed, inverting the condition")
        elif tok.type == tokenize.NAME and tok.string == "is" and nxt is not None and same_row:
            if nxt.string == "not":
                span(tok.start[1], nxt.end[1], "is", "flip_is", "`is not` becomes `is`")
            else:
                span(tok.start[1], tok.end[1], "is not", "flip_is", "`is` becomes `is not`")
        elif tok.type == tokenize.NAME and tok.string == "in" and prev is not None and prev.string != "not":
            comparison = (prev.type in (tokenize.NAME, tokenize.STRING, tokenize.NUMBER) and prev.string not in keyword.kwlist
                          ) or prev.string in (")", "]", "}")
            if comparison and not re.search(r"\bfor\b", lines[row - 1][: tok.start[1]]):
                span(tok.start[1], tok.end[1], "not in", "flip_in", "`in` becomes `not in`")
        elif tok.type == tokenize.OP and tok.string in ("+", "-") and prev is not None:
            binary = (prev.type in (tokenize.NAME, tokenize.NUMBER, tokenize.STRING) and prev.string not in keyword.kwlist
                      ) or prev.string in (")", "]", "}")
            if binary:
                other = "-" if tok.string == "+" else "+"
                span(tok.start[1], tok.end[1], other, "arith", f"`{tok.string}` becomes `{other}`", "D2")
        elif tok.type == tokenize.OP and tok.string in ("+=", "-="):
            other = "-=" if tok.string == "+=" else "+="
            span(tok.start[1], tok.end[1], other, "arith", f"`{tok.string}` becomes `{other}`", "D2")
        elif tok.type == tokenize.STRING and _plain_string(tok.string):
            line_text = lines[row - 1]
            first_on_line = prev is None or prev.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
            noisy = re.search(r"\b(raise|warn|warnings|msg|message|print|log)\b", line_text) or line_text.lstrip().startswith(
                ("@", "import ", "from "))
            if not first_on_line and not noisy:
                quote = tok.string[0]
                span(tok.start[1], tok.end[1], f"{quote}{tok.string[1:-1]}x{quote}", "string",
                     f"string {tok.string} becomes {quote}{tok.string[1:-1]}x{quote}", "D2")
    return found


def _plain_string(text: str) -> bool:
    """A short, unprefixed, single-line string literal: not a docstring, f-string, bytes or regex."""
    return bool(re.fullmatch(r"(['\"])[^'\"\\\n]{1,40}\1", text))


def _blocks(tree: ast.AST) -> list[list[ast.stmt]]:
    blocks: list[list[ast.stmt]] = []
    for node in ast.walk(tree):
        for name in ("body", "orelse", "finalbody"):
            block = getattr(node, name, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                blocks.append(block)
    return blocks


def statement_candidates(source: str) -> list[Candidate]:
    lines = source.splitlines()
    found: list[Candidate] = []
    for block in _blocks(ast.parse(source)):
        for stmt in block:
            only_raises = isinstance(stmt, ast.If) and not stmt.orelse and all(
                isinstance(s, ast.Raise) for s in stmt.body
            )
            if only_raises and len(block) > 1 and stmt.end_lineno:
                found.append(Candidate("D3", "drop_guard", stmt.lineno, stmt.end_lineno, [],
                                       f"the guard at line {stmt.lineno} is removed"))

        simple = (ast.Assign, ast.AugAssign, ast.Expr)
        for first, second in zip(block, block[1:], strict=False):
            if not (isinstance(first, simple) and isinstance(second, simple)):
                continue
            if first.lineno != first.end_lineno or second.lineno != second.end_lineno:
                continue
            if second.lineno != first.lineno + 1 or lines[first.lineno - 1] == lines[second.lineno - 1]:
                continue
            found.append(Candidate("D5", "swap_statements", first.lineno, second.lineno,
                                   [lines[second.lineno - 1], lines[first.lineno - 1]],
                                   f"lines {first.lineno} and {second.lineno} swap places"))

    tree = ast.parse(source)
    for block in _blocks(tree):
        for stmt in block:
            droppable = isinstance(stmt, (ast.Assign, ast.AugAssign)) or (
                isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call))
            dunder = isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id.startswith("__") for t in stmt.targets)
            if not droppable or dunder or not stmt.end_lineno:
                continue
            if len(block) > 1:
                found.append(Candidate("D3", "drop_statement", stmt.lineno, stmt.end_lineno, [],
                                       f"the statement at line {stmt.lineno} is removed"))
            else:                                     # deleting the only statement would leave an empty block
                indent = lines[stmt.lineno - 1][: stmt.col_offset]
                found.append(Candidate("D3", "pass_statement", stmt.lineno, stmt.end_lineno, [indent + "pass"],
                                       f"the statement at line {stmt.lineno} becomes `pass`"))

    for node in ast.walk(tree):
        if isinstance(node, ast.If) and node.test.lineno == node.test.end_lineno == node.lineno:
            text = lines[node.lineno - 1]
            end = node.test.end_col_offset
            if text.isascii() and end is not None and not isinstance(node.test, ast.Constant):
                changed = text[: node.test.col_offset] + "not (" + text[node.test.col_offset: end] + ")" + text[end:]
                found.append(Candidate("D4", "invert_condition", node.lineno, node.lineno, [changed],
                                       f"the condition at line {node.lineno} is inverted"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None and node.end_lineno == node.lineno:
            value = node.value
            text = lines[node.lineno - 1]
            plain = isinstance(value, ast.Name) or (isinstance(value, ast.Constant)
                                                    and value.value in (None, True, False))
            if not plain and text.isascii() and value.end_col_offset is not None and value.lineno == value.end_lineno:
                changed = text[: value.col_offset] + "None" + text[value.end_col_offset:]
                found.append(Candidate("D9", "return_none_expr", node.lineno, node.lineno, [changed],
                                       f"returns None instead of `{text[value.col_offset:value.end_col_offset]}`"))
        if isinstance(node, ast.Call) and len(node.args) >= 2 and node.lineno == node.end_lineno:
            arg0, arg1 = node.args[0], node.args[1]
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            text = lines[node.lineno - 1]
            if (name not in _NO_SWAP and text.isascii() and not isinstance(arg0, ast.Starred)
                    and not isinstance(arg1, ast.Starred) and arg0.end_col_offset is not None
                    and arg1.end_col_offset is not None and arg0.lineno == arg1.lineno == node.lineno):
                a, b = text[arg0.col_offset: arg0.end_col_offset], text[arg1.col_offset: arg1.end_col_offset]
                if a != b:
                    changed = (text[: arg0.col_offset] + b + text[arg0.end_col_offset: arg1.col_offset] + a
                               + text[arg1.end_col_offset:])
                    found.append(Candidate("D5", "swap_args", node.lineno, node.lineno, [changed],
                                           f"the first two arguments of `{name}` swap places"))
    return found


# Swapping these only raises a TypeError, which says nothing about the code under test.
_NO_SWAP = {"isinstance", "issubclass", "getattr", "hasattr", "setattr", "range", "slice", "enumerate", "zip", "format"}


_KEY_CALLS = {"sorted", "min", "max", "sort", "nsmallest", "nlargest"}


def _call_name(node: ast.Call) -> str:
    return node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")


def _int_bound(node: ast.expr | None) -> int | None:
    """The value of a slice bound written as an integer literal (`1`, `-1`); None for anything else."""
    def plain_int(n: ast.expr) -> bool:
        return isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)

    if node is not None and plain_int(node):
        return node.value  # type: ignore[attr-defined]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and plain_int(node.operand):
        return -node.operand.value  # type: ignore[attr-defined]
    return None


def argument_candidates(source: str) -> list[Candidate]:
    """Edits to arguments that the token and statement operators cannot reach.

    The iniconfig pilot had 7 of 20 rules with no DRIFT example because no operator touched what they cite:
    a boolean default or keyword (`strip_inline_comments=True`), the `key=` of a sort, a slice bound (`line[1:-1]`).

        flip_bool_arg   D2  a boolean parameter default or keyword argument becomes its opposite
        drop_key_arg    D3  `key=...` is removed from sorted / min / max / sort / nsmallest / nlargest
        shift_slice     D1  an integer slice bound moves one step further from zero
    """
    lines = source.splitlines()
    found: list[Candidate] = []

    def spliced(node: ast.expr, new: str) -> list[str] | None:
        """The node's line with the node's text replaced; None if it spans lines or the line is not ASCII."""
        if node.lineno != node.end_lineno or node.end_col_offset is None:
            return None
        text = lines[node.lineno - 1]
        if not text.isascii():
            return None
        return [text[: node.col_offset] + new + text[node.end_col_offset:]]

    def flip(value: ast.expr | None, what: str) -> None:
        if isinstance(value, ast.Constant) and isinstance(value.value, bool):
            new = "False" if value.value else "True"
            edit = spliced(value, new)
            if edit:
                found.append(Candidate("D2", "flip_bool_arg", value.lineno, value.lineno, edit, f"{what} becomes {new}"))

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spec = node.args
            positional = spec.posonlyargs + spec.args
            for arg, default in zip(positional[len(positional) - len(spec.defaults):], spec.defaults, strict=True):
                flip(default, f"the default of `{arg.arg}`")
            for kwonly, kw_default in zip(spec.kwonlyargs, spec.kw_defaults, strict=True):
                flip(kw_default, f"the default of `{kwonly.arg}`")
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg:
                    flip(kw.value, f"`{kw.arg}=`")
            text = lines[node.lineno - 1] if node.lineno == node.end_lineno else ""
            for kw in node.keywords:
                if (kw.arg != "key" or _call_name(node) not in _KEY_CALLS or not text or not text.isascii()
                        or kw.end_col_offset is None):
                    continue
                others: list[ast.expr | ast.keyword] = [*node.args, *node.keywords]
                before = [n.end_col_offset for n in others
                          if n is not kw and n.end_col_offset is not None and n.end_col_offset <= kw.col_offset]
                if before:
                    found.append(Candidate("D3", "drop_key_arg", node.lineno, node.lineno,
                                           [text[: max(before)] + text[kw.end_col_offset:]],
                                           f"`{_call_name(node)}` loses its `key=` argument"))
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            for which, bound in (("lower", node.slice.lower), ("upper", node.slice.upper)):
                number = _int_bound(bound)
                if bound is None or number is None:
                    continue
                shifted = number + 1 if number >= 0 else number - 1
                edit = spliced(bound, str(shifted))
                if edit:
                    found.append(Candidate("D1", "shift_slice", bound.lineno, bound.lineno, edit,
                                           f"the {which} slice bound {number} becomes {shifted}"))
    return found


def candidates_for(source: str) -> list[Candidate]:
    return token_candidates(source) + statement_candidates(source) + argument_candidates(source)


# --------------------------------------------------------------------------- patches


def make_patch(source: str, cand: Candidate) -> tuple[str, str] | None:
    """A (find, replace) pair matching `source` exactly once, widened with context if needed."""
    lines = source.splitlines()
    first, last = cand.line - 1, cand.end_line
    for pad in range(CONTEXT_LINES + 1):
        lo, hi = max(0, first - pad), min(len(lines), last + pad)
        find = "\n".join(lines[lo:hi])
        replace = "\n".join(lines[lo:first] + cand.new_lines + lines[last:hi])
        if find and find != replace and source.count(find) == 1:
            return find, replace
    return None


def enclosing_symbol(source: str, rel: str, line: int) -> str:
    inside = [c for c in chunk_source(source, rel) if c.start_line <= line <= c.end_line]
    return min(inside, key=lambda c: c.end_line - c.start_line).qualname if inside else "<module>"


def focus_lines(source: str, quotes: list[str]) -> set[int]:
    """1-based lines of `source` that contain one of `quotes` (whitespace-insensitive)."""
    wanted = [" ".join(q.split()) for q in quotes if q.strip()]
    return {
        number for number, line in enumerate(source.splitlines(), start=1)
        if any(q in " ".join(line.split()) for q in wanted)
    }


def sample(cands: list[Candidate], per_operator: int, rng: random.Random) -> list[Candidate]:
    """At most `per_operator` of each operator, chosen by the seeded generator, kept in line order."""
    by_op: dict[str, list[Candidate]] = {}
    for cand in cands:
        by_op.setdefault(cand.operator, []).append(cand)
    chosen: list[Candidate] = []
    for op in sorted(by_op):
        pool = by_op[op]
        chosen += pool if len(pool) <= per_operator else rng.sample(pool, per_operator)
    return sorted(chosen, key=lambda c: (c.line, c.operator))


# --------------------------------------------------------------------------- running the suite


def sandbox_wrap(cmd: list[str], mode: SandboxMode) -> tuple[list[str], bool]:
    """Wrap `cmd` so it has no network and may only write to scratch space. Returns (cmd, sandboxed)."""
    if mode == "off":
        return cmd, False
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        profile = (
            "(version 1)(allow default)(deny network*)(deny file-write*)"
            '(allow file-write* (subpath "/private/var/folders") (subpath "/private/tmp") (subpath "/dev"))'
        )
        return ["sandbox-exec", "-p", profile, *cmd], True
    if mode == "require":
        raise RuntimeError("no sandbox available on this system; refusing to run untrusted tests")
    return cmd, False


@dataclass
class PytestRun:
    status: Status | Literal["passed"]
    test: str = ""
    message: str = ""
    sandboxed: bool = False
    output: str = ""


def run_pytest(
    workdir: Path, timeout: float, mode: SandboxMode, targets: tuple[str, ...] = (), tb: str = "line"
) -> PytestRun:
    """Run pytest in `workdir` on `targets` (everything, if none) and classify the result."""
    cmd, sandboxed = sandbox_wrap(
        [sys.executable, "-m", "pytest", "-x", "-q", f"--tb={tb}", "-rf", "--no-header", "--disable-warnings",
         "-p", "no:cacheprovider", "-o", "addopts=", *targets],
        mode,
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join([str(workdir / "src"), str(workdir)]),
        "TMPDIR": tempfile.gettempdir(),
        # pytest cuts its summary line to the terminal width; "UnboundLocalError" must arrive whole.
        "COLUMNS": "2000",
    }
    try:
        proc = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return PytestRun("timeout", message="suite exceeded the time limit", sandboxed=sandboxed)

    return classify_run(proc.returncode, proc.stdout, proc.stderr, sandboxed)


def classify_run(returncode: int, stdout: str, stderr: str, sandboxed: bool = False) -> PytestRun:
    """passed, killed (an assertion failed) or crash (the code no longer loads, or pytest itself failed)."""
    if returncode == 0:
        return PytestRun("passed", sandboxed=sandboxed, output=stdout)
    failed = _FAILED_RE.search(stdout)
    test = failed["test"] if failed else ""
    message = (failed["message"] or "").strip() if failed else ""
    if returncode != 1 or not failed or message.startswith(CRASH_ERRORS):
        tail = (stdout + stderr).strip().splitlines()
        return PytestRun("crash", test, message or (tail[-1] if tail else "no output"), sandboxed, stdout)
    return PytestRun("killed", test, message, sandboxed, stdout)


def run_suite(workdir: Path, timeout: float, mode: SandboxMode) -> tuple[Status | Literal["passed"], str, str, bool]:
    """Run the project's whole suite. Returns (status, failing test, message, sandboxed)."""
    run = run_pytest(workdir, timeout, mode)
    return run.status, run.test, run.message, run.sandboxed


# --------------------------------------------------------------------------- driver


def is_test_project(project: Path, protected_roots: list[Path]) -> bool:
    resolved = project.resolve()
    return any(root.resolve() in (resolved, *resolved.parents) for root in protected_roots)


def source_files(project: Path, subdir: str) -> list[Path]:
    base = project / subdir
    skip = {"__pycache__", ".venv", "tests", "test"}
    return sorted(
        p for p in base.rglob("*.py")
        if not skip & set(p.relative_to(base).parts) and p.name != "conftest.py"
    )


def inject_project(
    project: Path,
    name: str,
    *,
    subdir: str = "src",
    only: tuple[str, ...] = (),
    focus: dict[str, list[str]] | None = None,
    benign: bool = False,
    per_operator: int = 6,
    seed: int = 17,
    timeout: float = 60.0,
    sandbox: SandboxMode = "auto",
    protected_roots: list[Path] | None = None,
    allow_test_project: bool = False,
) -> tuple[list[Mutant], dict]:
    project = project.resolve()
    if not allow_test_project and is_test_project(project, protected_roots or []):
        raise ValueError(f"{project} is part of the test set; refusing to generate training data from it")

    rng = random.Random(seed)
    mutants: list[Mutant] = []
    with tempfile.TemporaryDirectory(prefix="specdrift-inject-") as scratch:
        work = Path(scratch) / "p"
        shutil.copytree(project, work, ignore=IGNORED)

        status, test, message, sandboxed = run_suite(work, timeout, sandbox)
        if status != "passed":
            raise ProjectBroken(f"{name}: unmodified project does not pass its tests ({status}: {message or test})")

        for path in source_files(work, subdir):
            rel = path.relative_to(work).as_posix()
            if only and not any(rel.endswith(suffix) for suffix in only):
                continue
            original = path.read_text(encoding="utf-8")
            try:
                found = benign_candidates(original) if benign else candidates_for(original)
            except (SyntaxError, tokenize.TokenError):
                continue
            if focus is None:
                cands = sample(found, per_operator, rng)
            else:
                # Targeted: only the lines a rule cites, every operator that applies, no sampling cap.
                quotes = [q for suffix, qs in focus.items() if rel.endswith(suffix) for q in qs]
                lines = focus_lines(original, quotes)
                cands = [c for c in found if lines & set(range(c.line, c.end_line + 1))]
            for cand in cands:
                patch = make_patch(original, cand)
                if patch is None:
                    continue
                find, replace = patch
                try:
                    mutated = apply_patch(original, find, replace)
                except PatchError:
                    continue

                record: dict[str, Any] = dict(
                    project=name, category=cand.category, operator=cand.operator, file=rel, line=cand.line,
                    symbol=enclosing_symbol(original, rel, cand.line), find=find, replace=replace,
                    description=cand.description,
                )
                try:
                    compile(mutated, rel, "exec")
                except SyntaxError:
                    mutants.append(Mutant(mutant_id="", status="invalid", sandboxed=sandboxed, **record))
                    continue

                path.write_text(mutated, encoding="utf-8")
                try:
                    status, test, message, sandboxed = run_suite(work, timeout, sandbox)
                finally:
                    path.write_text(original, encoding="utf-8")
                if status == "passed":
                    status = "preserved" if cand.category in ("N2", "N3") else "survived"
                mutants.append(Mutant(
                    mutant_id="", status=status,
                    failing_test=test, failure_message=message[:300], sandboxed=sandboxed, **record,
                ))

    for number, mutant in enumerate(mutants, start=1):
        mutant.mutant_id = f"{name}-{mutant.category}-{number:03d}"
    stats = {
        "mutants": len(mutants),
        "by_status": dict(Counter(m.status for m in mutants)),
        "by_category": dict(sorted(Counter(m.category for m in mutants).items())),
        "killed_by_category": dict(sorted(Counter(m.category for m in mutants if m.status == "killed").items())),
        "sandboxed": all(m.sandboxed for m in mutants) if mutants else sandboxed,
        "seed": seed,
    }
    return mutants, stats


def write_mutants(mutants: list[Mutant], stats: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(m.model_dump_json() + "\n" for m in mutants), encoding="utf-8")
    out.with_suffix(".stats.json").write_text(json.dumps(stats, indent=2) + "\n")
