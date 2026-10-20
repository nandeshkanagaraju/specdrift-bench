from specdrift.bench.schema import CaseResult, Verdict
from specdrift.eval.stability import format_stability, score_runs
from specdrift.runner import available_runs, load_verdicts, verdicts_path


def _case(case_id, category, target=("R01",)):
    drift = category.startswith("D")
    return CaseResult(
        case_id=case_id, project="p", category=category, label="drift" if drift else "no_drift",
        status="valid", target_rules=list(target) if drift else [], workspace="/x",
    )


def _verdict(case_id, rule, verdict, run):
    return Verdict(case_id=case_id, rule_id=rule, detector="d", verdict=verdict, confidence=0.9, run=run)


def test_identical_runs_have_zero_spread_and_no_flips():
    cases = [_case("a", "D1"), _case("b", "N2")]
    run = [_verdict("a", "R01", "DRIFT", 1), _verdict("b", "R01", "COMPLIANT", 1)]
    report = score_runs(cases, {1: run, 2: run}, "d", n_boot=200)
    assert report["flip_rate"] == 0.0
    assert report["overall"]["recall"]["run_std"] == 0.0
    assert report["overall"]["recall"]["mean"] == 1.0


def test_disagreeing_runs_widen_the_interval_and_count_flips():
    cases = [_case(f"a{i}", "D1") for i in range(10)]
    hit = [_verdict(c.case_id, "R01", "DRIFT", 1) for c in cases]
    miss = [_verdict(c.case_id, "R01", "COMPLIANT", 2) for c in cases[:5]] + [
        _verdict(c.case_id, "R01", "DRIFT", 2) for c in cases[5:]
    ]
    report = score_runs(cases, {1: hit, 2: miss}, "d", n_boot=500)
    assert report["flip_rate"] == 0.5
    low, high = report["overall"]["recall"]["ci95"]
    assert low < report["overall"]["recall"]["mean"] < high
    assert "95% CI" in format_stability(report)


def test_score_runs_is_seeded():
    cases = [_case(f"a{i}", "D1") for i in range(6)]
    v = {1: [_verdict(c.case_id, "R01", "DRIFT" if i % 2 else "COMPLIANT", 1) for i, c in enumerate(cases)]}
    assert score_runs(cases, v, "d", n_boot=100) == score_runs(cases, v, "d", n_boot=100)


def test_repeat_runs_are_stored_beside_run_one(tmp_path):
    from specdrift.config import Settings

    settings = Settings(results_dir=tmp_path, cache_dir=tmp_path / "c")
    assert verdicts_path(settings, "d", 1).name == "verdicts.jsonl"
    assert verdicts_path(settings, "d", 3).name == "verdicts.run3.jsonl"
    for run in (1, 3):
        path = verdicts_path(settings, "d", run)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_verdict("a", "R01", "DRIFT", run).model_dump_json() + "\n")
    assert available_runs(settings, "d") == [1, 3]
    assert load_verdicts(settings, "d", 3)[0].run == 3
