from specdrift.bench.schema import CaseResult, Counterexample, Verdict
from specdrift.eval.metrics import case_outcome, score


def case(case_id, category, label, target_rules=(), gold="Service.borrow", status="valid"):
    return CaseResult(
        case_id=case_id, project="p", category=category, label=label,
        target_rules=list(target_rules), gold_symbol=gold, status=status,
    )


def verdict(case_id, rule_id, value, chunks=("src/a.py::Service.borrow",)):
    return Verdict(
        case_id=case_id, rule_id=rule_id, detector="d", verdict=value,
        confidence=0.8, violated_clause="c" if value == "DRIFT" else "",
        counterexample=Counterexample(input="i", actual="a") if value == "DRIFT" else Counterexample(),
        retrieved_chunks=list(chunks),
    )


def test_drift_flagged_on_its_target_rule_is_a_true_positive():
    row = case_outcome(case("c", "D1", "drift", ["R01"]), [verdict("c", "R01", "DRIFT")])
    assert row["outcome"] == "TP"


def test_drift_flagged_only_on_another_rule_is_still_a_miss():
    row = case_outcome(
        case("c", "D1", "drift", ["R01"]),
        [verdict("c", "R02", "DRIFT"), verdict("c", "R01", "COMPLIANT")],
    )
    assert row["outcome"] == "FN"
    assert row["spurious_rules"] == ["R02"]


def test_scope_creep_with_no_target_rule_accepts_any_flag():
    row = case_outcome(case("c", "D8", "drift", []), [verdict("c", "R09", "DRIFT")])
    assert row["outcome"] == "TP"


def test_any_flag_on_a_negative_control_is_a_false_alarm():
    row = case_outcome(case("c", "N2", "no_drift"), [verdict("c", "R01", "DRIFT")])
    assert row["outcome"] == "FP"


def test_clean_negative_control_is_a_true_negative():
    row = case_outcome(case("c", "N1", "no_drift"), [verdict("c", "R01", "COMPLIANT")])
    assert row["outcome"] == "TN"


def test_uncertain_does_not_count_as_a_flag():
    row = case_outcome(case("c", "N2", "no_drift"), [verdict("c", "R01", "UNCERTAIN")])
    assert row["outcome"] == "TN"
    assert row["uncertain"] == 1


def test_miss_with_the_gold_chunk_shown_is_a_reasoning_failure():
    row = case_outcome(case("c", "D1", "drift", ["R01"]), [verdict("c", "R01", "COMPLIANT")])
    assert row["attribution"] == "reasoning"


def test_miss_without_the_gold_chunk_is_a_retrieval_failure():
    row = case_outcome(
        case("c", "D1", "drift", ["R01"]),
        [verdict("c", "R01", "COMPLIANT", chunks=("src/a.py::Other.method",))],
    )
    assert row["attribution"] == "retrieval"


def test_detector_without_retrieval_is_not_blamed_for_retrieval():
    row = case_outcome(
        case("c", "D1", "drift", ["R01"]),
        [verdict("c", "R01", "COMPLIANT", chunks=())],
    )
    assert row["attribution"] == "n/a"


def test_invalid_cases_are_excluded_from_scoring():
    cases = [case("bad", "D1", "drift", ["R01"], status="invalid")]
    assert score(cases, [], "d")["cases_scored"] == 0


def test_overall_metrics_add_up():
    cases = [
        case("d1", "D1", "drift", ["R01"]),
        case("d2", "D2", "drift", ["R01"]),
        case("n1", "N1", "no_drift"),
        case("n2", "N2", "no_drift"),
    ]
    verdicts = [
        verdict("d1", "R01", "DRIFT"),       # TP
        verdict("d2", "R01", "COMPLIANT"),   # FN
        verdict("n1", "R01", "DRIFT"),       # FP
        verdict("n2", "R01", "COMPLIANT"),   # TN
    ]
    report = score(cases, verdicts, "d")

    assert report["counts"] == {"TP": 1, "FN": 1, "FP": 1, "TN": 1}
    assert report["overall"]["precision"] == 0.5
    assert report["overall"]["recall"] == 0.5
    assert report["overall"]["false_alarm_rate"] == 0.5


def test_per_category_uses_recall_for_drift_and_far_for_controls():
    cases = [case("d1", "D1", "drift", ["R01"]), case("n1", "N1", "no_drift")]
    verdicts = [verdict("d1", "R01", "DRIFT"), verdict("n1", "R01", "DRIFT")]
    report = score(cases, verdicts, "d")

    assert report["per_category"]["D1"]["metric"] == "recall"
    assert report["per_category"]["D1"]["value"] == 1.0
    assert report["per_category"]["N1"]["metric"] == "false alarm rate"
    assert report["per_category"]["N1"]["value"] == 1.0


def test_settings_env_file_is_anchored_to_repo_root():
    from specdrift.config import REPO_ROOT, Settings

    assert Settings.model_config["env_file"] == REPO_ROOT / ".env"


def _d8_case():
    from specdrift.bench.schema import CaseResult

    return CaseResult(
        case_id="w-D8-01", project="w", category="D8", label="drift", target_rules=[],
        gold_symbol="WalletService.overdraft", file="src/wallet/service.py", status="valid",
    )


def _flag(rule, chunks=(), file=""):
    from specdrift.bench.schema import Evidence, Verdict

    return Verdict(
        case_id="w-D8-01", rule_id=rule, detector="d", verdict="DRIFT", confidence=0.9,
        retrieved_chunks=list(chunks), evidence=Evidence(file=file),
    )


def test_d8_flag_raised_on_the_planted_code_counts():
    from specdrift.eval.metrics import case_outcome

    row = case_outcome(_d8_case(), [_flag("R03", chunks=["service.py::WalletService.overdraft"])])
    assert row["outcome"] == "TP"


def test_d8_flag_raised_elsewhere_is_spurious_not_a_hit():
    from specdrift.eval.metrics import case_outcome

    row = case_outcome(_d8_case(), [_flag("R03", chunks=["service.py::WalletService.deposit"])])
    assert row["outcome"] == "FN"
    assert row["spurious_rules"] == ["R03"]


def test_d8_falls_back_to_cited_file_then_to_benefit_of_the_doubt():
    from specdrift.eval.metrics import case_outcome

    assert case_outcome(_d8_case(), [_flag("R03", file="other.py")])["outcome"] == "FN"
    assert case_outcome(_d8_case(), [_flag("R03", file="src/wallet/service.py")])["outcome"] == "TP"
    assert case_outcome(_d8_case(), [_flag("R03")])["outcome"] == "TP"
