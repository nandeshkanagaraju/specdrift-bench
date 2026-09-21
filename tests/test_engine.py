"""End to end over the real host projects, with the offline model stand-in."""

from specdrift.bench.builder import build_case
from specdrift.bench.pipeline import build_one, summarise
from specdrift.bench.schema import CaseSpec
from specdrift.bench.validator import validate_case
from specdrift.eval.metrics import score
from specdrift.live import check_project
from specdrift.verify.engine import SpecGuard


def built(settings, case_id, category, label, find="", replace="", file="", rules=()):
    case = CaseSpec(
        id=case_id, project="library", category=category, label=label,
        file=file, find=find, replace=replace, target_rules=list(rules),
        gold_symbol="<module>" if file else "",
    )
    workspace = build_case(case, settings.projects_dir, settings.work_dir)
    return validate_case(case, workspace)


def test_specguard_emits_one_verdict_per_rule(settings):
    case = built(settings, "eng-1", "N1", "no_drift")
    verdicts = SpecGuard(settings).run_case(case)

    assert len(verdicts) == 14
    assert {v.case_id for v in verdicts} == {"eng-1"}
    assert all(v.retrieved_chunks for v in verdicts)


def test_specguard_does_not_flag_the_unchanged_project(settings):
    case = built(settings, "eng-clean", "N1", "no_drift")
    verdicts = SpecGuard(settings).run_case(case)
    assert [v.rule_id for v in verdicts if v.verdict == "DRIFT"] == []


def test_specguard_flags_a_changed_constant(settings):
    case = built(
        settings, "eng-drift", "D2", "drift",
        find="LOAN_PERIOD_DAYS = 14     # R12",
        replace="LOAN_PERIOD_DAYS = 21     # R12",
        file="src/library/service.py",
        rules=["R12"],
    )
    verdicts = SpecGuard(settings).run_case(case)
    r12 = next(v for v in verdicts if v.rule_id == "R12")

    assert r12.verdict == "DRIFT"
    assert r12.violated_clause
    assert r12.counterexample.input and r12.counterexample.actual


def test_a_repeat_run_is_served_from_the_cache(settings):
    case = built(settings, "eng-cache", "N1", "no_drift")
    detector = SpecGuard(settings)

    first = detector.run_case(case)
    second = detector.run_case(case)

    assert not any(v.cache_hit for v in first)
    assert all(v.cache_hit for v in second)


def test_scoring_a_real_case_pair(settings):
    clean = built(settings, "sc-clean", "N1", "no_drift")
    drifted = built(
        settings, "sc-drift", "D2", "drift",
        find="LOAN_PERIOD_DAYS = 14     # R12",
        replace="LOAN_PERIOD_DAYS = 21     # R12",
        file="src/library/service.py",
        rules=["R12"],
    )
    detector = SpecGuard(settings)
    verdicts = detector.run_case(clean) + detector.run_case(drifted)
    report = score([clean, drifted], verdicts, "specguard")

    assert report["counts"]["TP"] == 1
    assert report["counts"]["FP"] == 0


def test_live_check_reports_pass_on_a_clean_project(settings):
    _, summary = check_project(settings.projects_dir / "library", settings)
    assert summary["status"] in {"PASS", "NEEDS_HUMAN"}
    assert summary["counts"]["DRIFT"] == 0
    assert summary["rules"] == 14


def test_live_check_reports_drift_on_a_patched_workspace(settings):
    case = built(
        settings, "live-drift", "D2", "drift",
        find="LOAN_PERIOD_DAYS = 14     # R12",
        replace="LOAN_PERIOD_DAYS = 21     # R12",
        file="src/library/service.py",
        rules=["R12"],
    )
    verdicts, summary = check_project(settings.work_dir / case.case_id, settings)
    assert summary["status"] == "DRIFT"
    assert any(v.rule_id == "R12" and v.verdict == "DRIFT" for v in verdicts)


def test_build_one_records_a_broken_patch(settings):
    case = CaseSpec(
        id="broken", project="library", category="D1", label="drift",
        file="src/library/service.py", find="this text is not in the file", replace="x",
    )
    result = build_one(case, settings)
    assert result.status == "invalid"
    assert "patch failed" in result.error


def test_summary_reports_the_escapes_tests_rate(settings):
    clean = built(settings, "sum-clean", "N1", "no_drift")
    text = summarise([clean])
    assert "N1" in text and "1 valid" in text


def test_building_one_case_keeps_the_rest_of_built_jsonl(settings):
    """A filtered build must update its rows, not replace the file."""
    from specdrift.bench.pipeline import build_all, load_built

    build_all(settings, project="library", progress=False)
    after_library = {row.case_id for row in load_built(settings)}
    assert len(after_library) >= 28

    build_all(settings, case_id="library-D7-01", progress=False)
    after_single = {row.case_id for row in load_built(settings)}
    assert after_single == after_library


def test_running_one_project_keeps_other_verdicts(settings):
    """The same guarantee for verdicts: a partial run must not void the others."""
    from specdrift.bench.pipeline import build_all
    from specdrift.runner import load_verdicts, run_detector

    cases = build_all(settings, progress=False)
    library = [c for c in cases if c.project == "library"]
    wallet = [c for c in cases if c.project == "wallet"]

    run_detector("keyword", library, settings, progress=False)
    run_detector("keyword", wallet, settings, progress=False)

    projects = {v.case_id.split("-")[0] for v in load_verdicts(settings, "keyword")}
    assert projects == {"library", "wallet"}


def test_unmatched_build_filter_returns_nothing(settings):
    from specdrift.bench.pipeline import build_all

    assert build_all(settings, case_id="no-such-case", progress=False) == []
