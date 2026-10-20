from pathlib import Path

from specdrift.bench.ablate import LEFTOVER, strip_rule_ids, stripped_workspace
from specdrift.bench.schema import CaseResult
from specdrift.config import REPO_ROOT, Settings


def test_trailing_id_comment_is_removed_entirely():
    assert strip_rule_ids("MAX = 3      # R06\n") == "MAX = 3\n"


def test_prefix_ids_go_but_the_explanation_stays():
    assert strip_rule_ids("# R04/R05 - add 2 tokens per second") == "# add 2 tokens per second"
    assert strip_rule_ids('"""R01 - one bucket per client."""') == '"""one bucket per client."""'


def test_prose_references_are_removed():
    assert "R0" not in strip_rule_ids('"""Add a book. Enforces R04 and R05."""')
    assert "R1" not in strip_rule_ids('"""Borrow a book. Enforces R06 to R12."""')
    assert "R13" not in strip_rule_ids("Return a book and charge the late fee from R13.")


def test_no_rule_id_survives_in_any_host_project_source():
    for path in (REPO_ROOT / "projects").glob("*/src/**/*.py"):
        cleaned = strip_rule_ids(path.read_text(encoding="utf-8"))
        assert not LEFTOVER.search(cleaned), path
        compile(cleaned, str(path), "exec")        # the stripped file must still parse


def test_stripped_workspace_leaves_the_original_alone(tmp_path):
    original = tmp_path / "ws"
    (original / "src").mkdir(parents=True)
    (original / "src" / "m.py").write_text("X = 1  # R01\n")
    (original / "spec.md").write_text("- **R01** x is 1\n")
    case = CaseResult(case_id="c", workspace=str(original), status="valid")

    ablated = stripped_workspace(case, Settings(work_dir=tmp_path / "work"))

    assert (original / "src" / "m.py").read_text() == "X = 1  # R01\n"
    assert (Path(ablated.workspace) / "src" / "m.py").read_text() == "X = 1\n"
    assert "R01" in (Path(ablated.workspace) / "spec.md").read_text()   # the spec keeps its ids
