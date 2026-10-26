"""Stage A: turn Jin & Chen's paired data into training examples.

Each task has a correct and a bug-injected implementation of one natural-language
requirement. We keep a pair member only if its label can be defended:

* both sides must parse, and the buggy side must differ from the correct side;
* the correct side must pass the task's tests and the buggy side must fail them;
* a task whose tests are empty is dropped, because nothing then backs either label.

A DRIFT example carries a counterexample taken from the first assert that really fails.
The dataset has no per-clause annotation, so `violated_clause` is the requirement's first
sentence, recorded as such in `provenance.notes`.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import textwrap
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule
from specdrift.data.schema import Provenance, Target, TrainingExample

DATASETS = ("humaneval", "mbpp", "quixbugs")
CONFIDENCE = 0.9
VAL_PERCENT = 10
EXEC_TIMEOUT_S = 25
CHILD = Path(__file__).with_name("_exec_child.py")

# Code from a third-party repo is run only after this screen; anything touching the
# filesystem, network, processes or the interpreter itself is skipped, not executed.
_BANNED_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "ctypes", "urllib", "requests", "http",
    "pathlib", "importlib", "multiprocessing", "threading", "signal", "resource", "pickle",
}
_BANNED_CALLS = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint"}

_DEF_RE = re.compile(r"^\s*def\s+(\w+)\s*\(", re.MULTILINE)


@dataclass
class Stats:
    """What went in, what came out, and why the rest was dropped."""

    tasks: Counter = field(default_factory=Counter)
    written: Counter = field(default_factory=Counter)
    dropped: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        return {
            "tasks": dict(self.tasks),
            "written": dict(self.written),
            "dropped": dict(self.dropped),
        }


def function_name(declaration: str) -> str:
    """The target function is the last `def` in the declaration (it may follow helpers)."""
    names = _DEF_RE.findall(declaration)
    return names[-1] if names else ""


def assemble(declaration: str, solution: str) -> str:
    return (declaration + solution).strip("\n").rstrip()


def parses(code: str) -> bool:
    try:
        ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    return True


def same_modulo_whitespace(a: str, b: str) -> bool:
    return "".join(a.split()) == "".join(b.split())


def is_unsafe(code: str) -> bool:
    """True if the code imports or calls anything the screen does not allow."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return False  # an unparsable file is dropped elsewhere; it will never run
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] in _BANNED_MODULES for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in _BANNED_MODULES:
                return True
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _BANNED_CALLS:
                return True
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr != "__init__":
            return True
    return False


def clean_requirement(text: str) -> str:
    return textwrap.dedent(text or "").strip()


def first_sentence(text: str, limit: int = 200) -> str:
    """A verbatim prefix of `text`, so the validator's substring rule always holds."""
    head = text.split("\n\n", 1)[0]
    match = re.search(r"(?<=[.!?])\s", head)
    head = head[: match.start()] if match else head
    head = head.split("\n", 1)[0] if len(head) > limit else head
    return head[:limit].strip()


def changed_span(good: str, buggy: str) -> tuple[int, int]:
    """1-based line span of the buggy code that differs from the correct code.

    Removed lines have no position in the buggy code, so the span points at the line where
    the removal happened. If the diff is large the span covers its first hunk only.
    """
    a = [line.strip() for line in good.splitlines()]
    b = [line.strip() for line in buggy.splitlines()]
    total = max(len(b), 1)
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        start = min(j1 + 1, total)
        end = max(start, min(j2, total))
        return start, end
    return 1, total


def run_check(code: str, test: str, func: str) -> dict:
    """Run `test` against `code` in a fresh, isolated interpreter and return its report."""
    job = json.dumps({"code": code, "test": test, "func": func})
    with tempfile.TemporaryDirectory(prefix="specdrift-job-") as cwd:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(CHILD)],
                input=job,
                capture_output=True,
                text=True,
                timeout=EXEC_TIMEOUT_S,
                cwd=cwd,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"},
            )
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "timeout", "counterexample": None}
    lines = proc.stdout.strip().splitlines()
    if not lines:
        return {"status": "load_error", "error": (proc.stderr or "no output")[-200:], "counterexample": None}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"status": "load_error", "error": "unreadable child output", "counterexample": None}


def split_for(dataset: str, task_id: str) -> str:
    """Stable 90/10 split by task, so a task's correct and buggy sides never straddle it."""
    digest = hashlib.sha256(f"{dataset}/{task_id}".encode()).digest()
    return "val" if digest[0] * 100 // 256 < VAL_PERCENT else "train"


def _chunk(code: str, func: str, n: int) -> Chunk:
    return Chunk(
        id=f"solution.py::{func}",
        file="solution.py",
        qualname=func,
        start_line=1,
        end_line=max(n, 1),
        source=code,
    )


def _example(
    dataset: str, row: dict, variant: str, code: str, func: str, requirement: str, target: Target,
    method: str, notes: dict[str, str],
) -> TrainingExample:
    task = row["task_id"].replace("/", "-").lower()
    return TrainingExample(
        example_id=f"paper-{dataset}-{task}-{variant}",
        source="paper",
        split=split_for(dataset, row["task_id"]),  # type: ignore[arg-type]
        project_id=f"paper-{dataset}-{task}",
        rule=Rule(id="R01", text=requirement),
        chunks=[_chunk(code, func, len(code.splitlines()))],
        label=target.verdict,
        category="paper:" + row.get("bug_type", "") if variant == "buggy" else "paper:correct",
        target=target,
        provenance=Provenance(
            label_method=method,  # type: ignore[arg-type]
            generator=f"jin-chen-2026/{dataset}",
            notes=notes,
        ),
    )


def _counted(examples: list[TrainingExample], dataset: str, stats: Stats) -> list[TrainingExample]:
    for example in examples:
        stats.written[f"{dataset}/{example.label}"] += 1
    return examples


def convert_task(dataset: str, row: dict, stats: Stats, execute: bool = True) -> list[TrainingExample]:
    stats.tasks[dataset] += 1
    requirement = clean_requirement(row.get("text", ""))
    func = function_name(row.get("declaration", ""))
    good = assemble(row["declaration"], row["canonical_solution"])
    bad = assemble(row["declaration"], row["buggy_solution"])

    if not requirement or not func:
        stats.dropped["task: no requirement or function"] += 1
        return []
    if not parses(good):
        stats.dropped["task: correct code does not parse"] += 1
        return []
    if is_unsafe(good) or is_unsafe(bad) or is_unsafe(row.get("test", "")):
        stats.dropped["task: failed the safety screen"] += 1
        return []

    method = "paper_pairing"
    if execute:
        report = run_check(good, row["test"], func)
        if report["status"] == "no_tests":
            stats.dropped["task: tests are empty"] += 1
            return []
        if report["status"] != "passed":
            stats.dropped["task: correct code fails its own tests"] += 1
            return []
        method = "test_suite"

    out = [
        _example(
            dataset, row, "correct", good, func, requirement,
            Target(verdict="COMPLIANT", confidence=CONFIDENCE),
            method, {"bug_type": "", "clause_method": "n/a"},
        )
    ]

    if not parses(bad):
        stats.dropped["buggy: does not parse"] += 1
    elif same_modulo_whitespace(good, bad):
        stats.dropped["buggy: identical to correct code"] += 1
    else:
        counter = Counterexample(
            input="(test harness)", expected="all tests pass",
            actual=row.get("failure_symptoms", "") or "test failure",
        )
        cx_method = "failure_symptoms"
        if execute:
            report = run_check(bad, row["test"], func)
            if report["status"] == "passed":
                stats.dropped["buggy: passes the tests"] += 1
                return _counted(out, dataset, stats)
            if report["status"] == "load_error":
                stats.dropped["buggy: fails to load"] += 1
                return _counted(out, dataset, stats)
            if report.get("counterexample"):
                counter = Counterexample(**report["counterexample"])
                cx_method = "assert_extracted"
            else:
                counter = Counterexample(
                    input="(test harness)", expected="all tests pass", actual=report.get("error", "test failure")
                )
                cx_method = "error_text"
        start, end = changed_span(good, bad)
        target = Target(
            verdict="DRIFT",
            confidence=CONFIDENCE,
            violated_clause=first_sentence(requirement),
            evidence=Evidence(file="solution.py", start_line=start, end_line=end),
            counterexample=counter,
        )
        out.append(
            _example(
                dataset, row, "buggy", bad, func, requirement, target, method,
                {
                    "bug_type": row.get("bug_type", ""),
                    "failure_symptoms": row.get("failure_symptoms", ""),
                    "clause_method": "first_sentence",
                    "counterexample_method": cx_method,
                },
            )
        )
    return _counted(out, dataset, stats)


def read_rows(src: Path, dataset: str) -> Iterator[dict]:
    path = src / "dataset" / dataset / f"{dataset}.jsonl"
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def convert(src: Path, out_path: Path, execute: bool = True, limit: int = 0) -> Stats:
    """Convert every dataset under `src` and write one JSONL file."""
    stats = Stats()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for dataset in DATASETS:
            for count, row in enumerate(read_rows(src, dataset)):
                if limit and count >= limit:
                    break
                for example in convert_task(dataset, row, stats, execute=execute):
                    handle.write(example.model_dump_json() + "\n")
    out_path.with_suffix(".stats.json").write_text(json.dumps(stats.as_dict(), indent=2) + "\n")
    return stats
