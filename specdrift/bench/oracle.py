"""Oracle tests: independent evidence that a drift case really violates its spec.

``escapes_tests`` says the host project's own suite still passes after an injection; that
alone cannot tell a genuine violation from a patch that changed nothing observable. An
oracle is a small pytest file, one per escaping drift case, that states the spec's
behaviour. It must pass on the pristine project and fail on the drifted workspace.

Verdicts, per case:

* ``confirmed``           passes on the pristine project, fails on the drifted one
* ``not_distinguishable`` passes on both: the drift changes no behaviour the oracle can see
* ``unreliable``          fails on the pristine project: the oracle itself is wrong
* ``waived``              no oracle can exist; ``cases/oracles/waivers.yaml`` says why
* ``missing``             an escaping drift case with neither an oracle nor a waiver
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from specdrift.bench.schema import CaseResult
from specdrift.config import Settings

ORACLE_TIMEOUT_S = 60


def oracles_dir(settings: Settings) -> Path:
    return settings.cases_dir / "oracles"


def load_waivers(settings: Settings) -> dict[str, str]:
    path = oracles_dir(settings) / "waivers.yaml"
    if not path.exists():
        return {}
    return {k: " ".join(str(v).split()) for k, v in (yaml.safe_load(path.read_text()) or {}).items()}


def needs_oracle(case: CaseResult) -> bool:
    """Only drift that survives the project's own tests is unproven without one."""
    return case.is_drift and case.status == "valid" and case.escapes_tests is True


def run_oracle(oracle: Path, root: Path) -> tuple[bool, str]:
    """Run one oracle file against the project rooted at `root`. Returns (passed, detail)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", str(root / "pytest.ini"),
         "--rootdir", str(root), str(oracle.resolve())],
        cwd=root, capture_output=True, text=True, timeout=ORACLE_TIMEOUT_S,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    tail = (proc.stdout or proc.stderr).strip().splitlines()
    return proc.returncode == 0, tail[-1][:300] if tail else ""


def check_oracle(case: CaseResult, settings: Settings) -> dict:
    """Verify the oracle for one case. Returns {status, detail}."""
    waivers = load_waivers(settings)
    oracle = oracles_dir(settings) / f"{case.case_id}.py"

    if case.case_id in waivers:
        return {"status": "waived", "detail": waivers[case.case_id]}
    if not oracle.exists():
        return {"status": "missing", "detail": f"no {oracle.name} and no waiver"}

    pristine_ok, pristine_detail = run_oracle(oracle, settings.projects_dir / case.project)
    if not pristine_ok:
        return {"status": "unreliable", "detail": f"fails on the pristine project: {pristine_detail}"}

    drifted_ok, drifted_detail = run_oracle(oracle, Path(case.workspace))
    if drifted_ok:
        return {"status": "not_distinguishable", "detail": "passes on the drifted workspace too"}
    return {"status": "confirmed", "detail": drifted_detail}
