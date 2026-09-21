from specdrift.bench.builder import build_case
from specdrift.bench.schema import CaseSpec
from specdrift.bench.validator import compiles, validate_case


def make(case_id, category, label, find, replace, file="src/library/service.py"):
    return CaseSpec(
        id=case_id, project="library", category=category, label=label,
        file=file, find=find, replace=replace,
    )


def test_compiles_accepts_valid_python(tmp_path):
    path = tmp_path / "ok.py"
    path.write_text("x = 1\n")
    assert compiles(path)[0] is True


def test_compiles_rejects_broken_python(tmp_path):
    path = tmp_path / "bad.py"
    path.write_text("def broken(:\n")
    ok, detail = compiles(path)
    assert ok is False and detail


def test_uncompilable_patch_is_invalid(settings):
    case = make("bad-1", "D3", "drift", "        return member", "        return member(")
    workspace = build_case(case, settings.projects_dir, settings.work_dir)
    result = validate_case(case, workspace)
    assert result.status == "invalid"
    assert "does not compile" in result.error


def test_negative_control_that_breaks_tests_is_invalid(settings):
    # A "refactor" that is not one: the loan cap silently changes.
    case = make("fake-refactor", "N2", "no_drift",
                "MAX_ACTIVE_LOANS = 3      # R06", "MAX_ACTIVE_LOANS = 9      # R06")
    workspace = build_case(case, settings.projects_dir, settings.work_dir)
    result = validate_case(case, workspace)
    assert result.status == "invalid"
    assert "negative control" in result.error


def test_drift_that_passes_tests_is_valid_and_marked(settings):
    case = make("creep-1", "D8", "drift",
                "    def list_loans(self, member_id: str) -> list[Loan]:",
                "    def renew(self):\n        return None\n\n"
                "    def list_loans(self, member_id: str) -> list[Loan]:")
    workspace = build_case(case, settings.projects_dir, settings.work_dir)
    result = validate_case(case, workspace)
    assert result.status == "valid"
    assert result.escapes_tests is True


def test_unchanged_control_passes(settings):
    case = CaseSpec(id="n1", project="library", category="N1", label="no_drift")
    workspace = build_case(case, settings.projects_dir, settings.work_dir)
    result = validate_case(case, workspace)
    assert result.status == "valid"
    assert result.escapes_tests is True
