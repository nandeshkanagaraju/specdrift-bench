import json

import pytest
from typer.testing import CliRunner

from specdrift import cli
from specdrift.bench.schema import Verdict
from specdrift.config import Settings
from specdrift.eval.heldout import (
    EXAMPLES_DIR,
    available_heldout_runs,
    heldout_pairs,
    load_expected,
    load_heldout,
    run_heldout,
    score_heldout,
    unscored_projects,
)

runner = CliRunner()
N_BOOT = 60
EXPECTED = {"p": {"R01", "R02"}, "q": set()}


def v(project, rule, verdict, confidence, run=1):
    return Verdict(case_id=project, rule_id=rule, detector="x", verdict=verdict, confidence=confidence, run=run)


RUN1 = [
    v("p", "R01", "DRIFT", 0.9),          # TP
    v("p", "R02", "COMPLIANT", 0.8),      # FN
    v("p", "R03", "DRIFT", 0.7),          # FP
    v("q", "R01", "COMPLIANT", 0.9),      # TN
]


def test_truth_comes_from_expected_json_and_a_missing_drift_verdict_is_an_abstention():
    pairs = heldout_pairs(EXPECTED, {1: [x for x in RUN1 if x.rule_id != "R02"]})
    missing = next(p for p in pairs if p["unit"] == "p:R02")
    assert missing == {"unit": "p:R02", "run": 1, "truth": "DRIFT", "verdict": "UNCERTAIN", "confidence": 0.0}
    assert next(p for p in pairs if p["unit"] == "p:R03")["truth"] == "COMPLIANT"
    assert all(p["unit"].split(":")[0] in EXPECTED for p in pairs)


def test_verdicts_for_projects_without_ground_truth_are_not_scored():
    stray = RUN1 + [v("clinic-desk", "R01", "DRIFT", 0.9)]
    assert not any(p["unit"].startswith("clinic-desk") for p in heldout_pairs(EXPECTED, {1: stray}))


def test_scores_are_per_rule_with_recall_precision_false_alarms_and_uncertain_rate():
    report = score_heldout(EXPECTED, {1: RUN1}, "arm", n_boot=N_BOOT)
    overall = report["overall"]
    assert overall["recall"]["mean"] == 0.5 and overall["precision"]["mean"] == 0.5
    assert overall["false_alarm_rate"]["mean"] == 0.5          # p:R03 flagged, q:R01 clean
    assert report["uncertain_rate"]["mean"] == 0.0
    assert report["drift_rules"] == 2 and report["rules"] == 4 and report["per_run"][0]["counts"]["TP"] == 1
    assert report["calibration"]["answered"] == 4 and report["abstention"]["curve"][0]["answered"] == 4

    missing = score_heldout(EXPECTED, {1: [x for x in RUN1 if x.rule_id != "R02"]}, "arm", n_boot=N_BOOT)
    assert missing["uncertain_rate"]["mean"] == 0.25 and missing["overall"]["recall"]["mean"] == 0.5


def test_runs_are_pooled_and_reported_one_by_one():
    run2 = [v("p", "R01", "DRIFT", 0.9, run=2), v("p", "R02", "DRIFT", 0.9, run=2),
            v("q", "R01", "COMPLIANT", 0.9, run=2)]
    report = score_heldout(EXPECTED, {1: RUN1, 2: run2}, "arm", n_boot=N_BOOT)
    assert [row["recall"] for row in report["per_run"]] == [0.5, 1.0]
    assert report["overall"]["recall"]["mean"] == 0.75
    with pytest.raises(ValueError, match="no held-out verdicts"):
        score_heldout(EXPECTED, {}, "arm")


def test_ground_truth_covers_three_of_the_four_test_2_projects():
    expected = load_expected()
    assert set(expected) == {"shop-checkout", "auth-gateway", "task-queue"}
    assert expected["task-queue"] == {"R01", "R06", "R08"}
    # clinic-desk is one of the four test-2 projects but has no entry; sample-project is frozen but is not one of them.
    assert unscored_projects(expected) == ["clinic-desk", "sample-project"]


def test_unscored_projects_ignores_folders_without_a_spec(tmp_path):
    for name, has_spec in (("a", True), ("b", True), ("c", False)):
        (tmp_path / name).mkdir()
        if has_spec:
            (tmp_path / name / "spec.md").write_text("- **R01** x MUST y.\n")
    assert unscored_projects({"a": {"R01"}}, tmp_path) == ["b"]


@pytest.fixture
def fake_settings(tmp_path):
    return Settings(llm_provider="fake", results_dir=tmp_path / "results", cache_dir=tmp_path / "cache",
                    work_dir=tmp_path / "work")


def test_a_later_run_is_a_real_run_and_not_the_cached_first_one(fake_settings):
    first, _ = run_heldout(fake_settings, 1, ["task-queue"])
    again, _ = run_heldout(fake_settings, 1, ["task-queue"])
    second, stats = run_heldout(fake_settings, 2, ["task-queue"])

    assert first and all(x.case_id == "task-queue" and x.run == 1 for x in first)
    assert all(x.cache_hit for x in again)                            # same run: answered from the cache
    assert all(x.run == 2 and not x.cache_hit for x in second)        # run 2 bypasses it
    assert stats == {"projects": ["task-queue"], "verdicts": len(second), "model": "fake", "run": 2}
    assert available_heldout_runs(fake_settings, "specguard") == [1, 2]
    assert [x.verdict for x in load_heldout(fake_settings, "specguard", 2)] == [x.verdict for x in second]


def test_an_unknown_project_is_refused(fake_settings):
    with pytest.raises(ValueError, match="clinic-desk"):
        run_heldout(fake_settings, 1, ["clinic-desk"])


def test_the_examples_are_only_read_never_written(fake_settings):
    before = {p: p.stat().st_mtime_ns for p in EXAMPLES_DIR.rglob("*") if p.is_file()}
    run_heldout(fake_settings, 1, ["shop-checkout"])
    assert before == {p: p.stat().st_mtime_ns for p in EXAMPLES_DIR.rglob("*") if p.is_file()}


def test_cli_stores_one_file_per_run(fake_settings, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: fake_settings)
    result = runner.invoke(cli.app, ["heldout", "--project", "task-queue", "--repeat", "2"])

    assert result.exit_code == 0, result.output
    assert "not scored" in result.output and "clinic-desk" in result.output
    assert available_heldout_runs(fake_settings, "specguard") == [1, 2]
    line = json.loads(fake_settings.detector_dir("specguard").joinpath("heldout.run2.jsonl").read_text().splitlines()[0])
    assert line["case_id"] == "task-queue" and line["run"] == 2
