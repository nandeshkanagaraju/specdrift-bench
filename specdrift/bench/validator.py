"""Check that a built case is usable, and record whether it escapes the test suite.

A case is only worth scoring if the patch compiled. Beyond that we record
``escapes_tests``: whether the host project's own pytest suite still passes after the
injection. That number is the evidence behind "drift passes tests".
"""

from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

from specdrift.bench.schema import CaseResult, CaseSpec

TEST_TIMEOUT_S = 60


def compiles(path: str | Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(path), doraise=True, cfile=str(Path(path).with_suffix(".pyc-check")))
        Path(str(Path(path).with_suffix(".pyc-check"))).unlink(missing_ok=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc).strip().splitlines()[-1][:300]


def run_tests(workspace: str | Path, timeout: int = TEST_TIMEOUT_S) -> tuple[bool, str]:
    """Run the workspace's own pytest suite. Returns (passed, detail)."""
    workspace = Path(workspace)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"pytest timed out after {timeout}s"

    tail = (proc.stdout or proc.stderr).strip().splitlines()
    return proc.returncode == 0, tail[-1][:300] if tail else ""


def validate_case(case: CaseSpec, workspace: str | Path) -> CaseResult:
    workspace = Path(workspace)
    result = CaseResult(
        case_id=case.id,
        project=case.project,
        category=case.category,
        label=case.label,
        target_rules=list(case.target_rules),
        gold_symbol=case.gold_symbol,
        file=case.file,
        note=case.note,
        workspace=str(workspace),
    )

    # Every changed file must still compile, or the case teaches nothing.
    if case.file:
        ok, detail = compiles(workspace / case.file)
        if not ok:
            result.status = "invalid"
            result.error = f"does not compile: {detail}"
            return result

    passed, detail = run_tests(workspace)
    result.escapes_tests = passed

    # A negative control that breaks the suite is a mislabelled case, not a refactor.
    if not case.is_drift and not passed:
        result.status = "invalid"
        result.error = f"negative control fails its own tests: {detail}"

    return result
