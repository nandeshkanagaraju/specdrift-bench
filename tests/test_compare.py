import json

import pytest

from specdrift.bench.schema import CaseResult, Verdict
from specdrift.eval.compare import (
    arm_report,
    bootstrap_ci,
    coverage_accuracy_curve,
    expected_calibration_error,
    paired_difference,
    scored_pairs,
)

N_BOOT = 60


def case(case_id, category, label, targets=()):
    return CaseResult(case_id=case_id, project="p", category=category, label=label, target_rules=list(targets))


CASES = [
    case("c1", "D1", "drift", ["R01"]),
    case("c2", "D2", "drift", ["R02"]),
    case("c3", "N1", "no_drift"),
    case("c4", "N1", "no_drift"),
    case("c5", "D8", "drift"),                       # scope creep: no target rule, so no per-rule truth
]


def v(case_id, rule, verdict, confidence, direction="forward", run=1):
    return Verdict(case_id=case_id, rule_id=rule, detector="x", verdict=verdict, confidence=confidence,
                   direction=direction, run=run)


# 8 scored pairs: 2 DRIFT truths, 6 COMPLIANT truths; 5 right, 2 wrong, 1 abstention.
RUN1 = [
    v("c1", "R01", "DRIFT", 0.9), v("c1", "R02", "COMPLIANT", 0.8),
    v("c2", "R01", "COMPLIANT", 0.6), v("c2", "R02", "COMPLIANT", 0.7),
    v("c3", "R01", "DRIFT", 0.95), v("c3", "R02", "COMPLIANT", 0.9),
    v("c4", "R01", "UNCERTAIN", 0.2), v("c4", "R02", "COMPLIANT", 0.85),
    v("c5", "R01", "DRIFT", 0.9),                    # excluded: D8 has no per-rule truth
    v("c1", "R01", "DRIFT", 0.9, direction="reverse"),   # excluded: reverse verdicts have no rule truth
]


def test_truth_is_drift_only_for_target_rules_and_d8_and_reverse_are_left_out():
    pairs = scored_pairs(CASES, {1: RUN1})
    assert len(pairs) == 8
    truths = {(p["unit"], i): p["truth"] for i, p in enumerate(pairs)}
    assert sorted(p["truth"] for p in pairs).count("DRIFT") == 2
    assert [p["unit"] for p in pairs if p["truth"] == "DRIFT"] == ["c1", "c2"]
    assert truths
    assert all(p["unit"] != "c5" for p in pairs)


def test_curve_reports_coverage_accuracy_recall_and_false_alarms_against_all_pairs():
    curve = {row["threshold"]: row for row in coverage_accuracy_curve(scored_pairs(CASES, {1: RUN1}))}

    assert curve[0.0] == {"threshold": 0.0, "answered": 7, "coverage": 0.875, "accuracy": 0.7143,
                          "recall": 0.5, "false_alarm_rate": 0.1667}
    assert curve[0.8]["answered"] == 5 and curve[0.8]["accuracy"] == 0.8 and curve[0.8]["coverage"] == 0.625
    # Only the confident false alarm survives at 0.95: accuracy collapses, recall is lost, the alarm stays.
    assert curve[0.95] == {"threshold": 0.95, "answered": 1, "coverage": 0.125, "accuracy": 0.0,
                           "recall": 0.0, "false_alarm_rate": 0.1667}


def test_curve_is_thinned_but_keeps_both_ends():
    pairs = [{"unit": str(i), "run": 1, "truth": "COMPLIANT", "verdict": "COMPLIANT", "confidence": i / 100}
             for i in range(1, 100)]
    curve = coverage_accuracy_curve(pairs, max_points=5)
    assert len(curve) == 5 and curve[0]["threshold"] == 0.0 and curve[-1]["threshold"] == 0.99
    assert coverage_accuracy_curve([]) == []


def test_ece_weights_bins_by_size_and_leaves_abstentions_out():
    result = expected_calibration_error(scored_pairs(CASES, {1: RUN1}))
    assert result["answered"] == 7                                  # the UNCERTAIN pair is not calibrated
    assert result["ece"] == pytest.approx(2.2 / 7, abs=1e-4)
    assert sum(b["n"] for b in result["bins"]) == 7


def test_ece_puts_a_confidence_of_one_in_the_top_bin_and_is_zero_when_calibrated():
    perfect = [{"unit": "a", "run": 1, "truth": "DRIFT", "verdict": "DRIFT", "confidence": 1.0}] * 4
    assert expected_calibration_error(perfect)["ece"] == 0.0
    assert expected_calibration_error(perfect)["bins"][0]["high"] == 1.0
    overconfident = [{"unit": "a", "run": 1, "truth": "COMPLIANT", "verdict": "DRIFT", "confidence": 1.0}] * 3
    assert expected_calibration_error(overconfident)["ece"] == 1.0
    assert expected_calibration_error([])["ece"] is None


def test_arm_report_adds_strict_precision_uncertain_rate_curve_and_ece():
    report = arm_report(CASES, {1: RUN1}, "arm", n_boot=N_BOOT)

    # Case level: c1 TP, c2 FN, c3 FP, c4 TN, and c5 TP (its flag sits on a D8 case and nothing contradicts that
    # it is localised), no spurious flags -> strict precision 2 / (2 + 1).
    assert report["extra"]["strict_precision"]["mean"] == round(2 / 3, 4)
    assert report["extra"]["uncertain_rate"]["mean"] == round(1 / 10, 4)    # 1 UNCERTAIN of 10 verdicts
    for key in ("strict_precision", "uncertain_rate"):
        low, high = report["extra"][key]["ci95"]
        assert 0 <= low <= high <= 1
    assert report["stability"]["overall"]["recall"]["mean"] == round(2 / 3, 4)
    assert report["abstention"]["pairs"] == 8 and report["abstention"]["curve"][0]["answered"] == 7
    assert report["calibration"]["ece"] == pytest.approx(2.2 / 7, abs=1e-4) and len(report["calibration"]["ece_ci95"]) == 2


def test_a_flag_on_a_non_target_rule_of_a_drift_case_lowers_strict_precision_only():
    noisy = RUN1 + [v("c1", "R02", "DRIFT", 0.7)]                  # spurious flag on a drift case
    noisy = [x for x in noisy if not (x.case_id == "c1" and x.rule_id == "R02" and x.verdict == "COMPLIANT")]
    report = arm_report(CASES, {1: noisy}, "arm", n_boot=N_BOOT)
    assert report["extra"]["strict_precision"]["mean"] == 0.5               # 2 / (2 TP + 1 FP + 1 spurious)
    assert report["stability"]["overall"]["precision"]["mean"] == round(2 / 3, 4)    # spurious flags are not FP


def test_paired_difference_is_arm_minus_baseline_on_the_same_cases():
    flag_everything = [v(c.case_id, rule, "DRIFT", 0.9) for c in CASES for rule in ("R01", "R02")]
    diff = paired_difference(CASES, {1: RUN1}, {1: flag_everything}, n_boot=N_BOOT)

    assert diff["cases"] == 5
    assert diff["false_alarm_rate"]["difference"] == -0.5            # arm 1 of 2 clean cases flagged, baseline both
    assert diff["recall"]["difference"] == pytest.approx(-1 / 3, abs=1e-4)      # arm catches 2 of 3, baseline all 3
    assert len(diff["false_alarm_rate"]["ci95"]) == 2
    flipped = paired_difference(CASES, {1: flag_everything}, {1: RUN1}, n_boot=N_BOOT)
    assert flipped["false_alarm_rate"]["difference"] == 0.5


def test_bootstrap_interval_is_reproducible_and_ignores_undefined_resamples():
    units = [str(i) for i in range(20)]
    first = bootstrap_ci(units, lambda s: sum(int(u) for u in s) / len(s), n_boot=100, seed=3)
    assert first == bootstrap_ci(units, lambda s: sum(int(u) for u in s) / len(s), n_boot=100, seed=3)
    assert bootstrap_ci([], lambda s: 1.0) is None
    assert bootstrap_ci(units, lambda s: None) is None
    assert json.dumps(first)
