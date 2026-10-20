from pathlib import Path

from specdrift.bench.oracle import check_oracle, needs_oracle
from specdrift.bench.schema import CaseResult
from specdrift.config import Settings

ORACLE = "from pkg import VALUE\n\n\ndef test_value():\n    assert VALUE == 1\n"


def _project(root: Path, value: int) -> Path:
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "__init__.py").write_text(f"VALUE = {value}\n")
    (root / "pytest.ini").write_text("[pytest]\npythonpath = src\n")
    return root


def _setup(tmp_path, drifted_value, pristine_value=1, waiver=""):
    _project(tmp_path / "projects" / "p", pristine_value)
    workspace = _project(tmp_path / "ws", drifted_value)
    (tmp_path / "cases" / "oracles").mkdir(parents=True)
    (tmp_path / "cases" / "oracles" / "p-D1-01.py").write_text(ORACLE)
    if waiver:
        (tmp_path / "cases" / "oracles" / "waivers.yaml").write_text(waiver)
    settings = Settings(projects_dir=tmp_path / "projects", cases_dir=tmp_path / "cases")
    case = CaseResult(case_id="p-D1-01", project="p", category="D1", label="drift",
                      status="valid", escapes_tests=True, workspace=str(workspace))
    return case, settings


def test_oracle_that_fails_only_on_the_drifted_workspace_is_confirmed(tmp_path):
    case, settings = _setup(tmp_path, drifted_value=2)
    assert check_oracle(case, settings)["status"] == "confirmed"


def test_oracle_that_passes_on_the_drifted_workspace_is_not_distinguishable(tmp_path):
    case, settings = _setup(tmp_path, drifted_value=1)
    assert check_oracle(case, settings)["status"] == "not_distinguishable"


def test_oracle_that_fails_on_the_pristine_project_is_unreliable(tmp_path):
    case, settings = _setup(tmp_path, drifted_value=2, pristine_value=3)
    assert check_oracle(case, settings)["status"] == "unreliable"


def test_waiver_and_missing_oracle(tmp_path):
    case, settings = _setup(tmp_path, drifted_value=1, waiver="p-D1-01: no observable change\n")
    assert check_oracle(case, settings) == {"status": "waived", "detail": "no observable change"}

    (settings.cases_dir / "oracles" / "p-D1-01.py").unlink()
    (settings.cases_dir / "oracles" / "waivers.yaml").unlink()
    assert check_oracle(case, settings)["status"] == "missing"


def test_only_drift_that_escapes_the_tests_needs_an_oracle():
    drift = CaseResult(case_id="a", label="drift", status="valid", escapes_tests=True)
    caught = CaseResult(case_id="b", label="drift", status="valid", escapes_tests=False)
    control = CaseResult(case_id="c", label="no_drift", status="valid", escapes_tests=True)
    assert [needs_oracle(c) for c in (drift, caught, control)] == [True, False, False]


def test_every_escaping_drift_case_in_the_repo_has_an_oracle_or_a_waiver():
    from specdrift.bench.pipeline import load_built
    from specdrift.config import get_settings

    settings = get_settings()
    for case in load_built(settings):
        if needs_oracle(case):
            assert check_oracle(case, settings)["status"] in {"confirmed", "waived"}, case.case_id
