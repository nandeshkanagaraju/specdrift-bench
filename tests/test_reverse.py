import json

from specdrift.bench.pipeline import build_all, load_built
from specdrift.bench.schema import CaseResult, Chunk, Verdict
from specdrift.cache import ResponseCache
from specdrift.code.chunker import chunk_workspace
from specdrift.eval.metrics import case_outcome
from specdrift.registry import build_detector
from specdrift.spec.parser import load_project_rules
from specdrift.verify.llm import FakeLLM
from specdrift.verify.reverse import (
    audit_chunk,
    is_function_chunk,
    locate_quote,
    reviewable_chunks,
    to_reverse_verdict,
)

CHUNK = Chunk(
    id="svc.py::Svc.renew", file="svc.py", qualname="Svc.renew", start_line=10, end_line=14,
    source="def renew(self, loan):\n    loan.due = loan.due + 14\n    return loan\n",
)


def _answer(**kw):
    base = {"verdict": "UNAUTHORISED", "confidence": 0.8, "behaviour": "extends a loan",
            "quote": "loan.due = loan.due + 14", "closest_rule": "none"}
    return base | kw


def test_only_functions_and_methods_are_reviewed(library_dir):
    chunks = chunk_workspace(library_dir)
    names = {c.qualname for c in reviewable_chunks(chunks)}
    assert "LibraryService.borrow" in names and "late_fee" in names
    assert "LibraryService.__init__" not in names          # dunder: only wires up state
    assert "<module>" not in names and "LibraryService" not in names   # module constants, class header
    assert not any(is_function_chunk(c) for c in chunks if c.qualname in ("<module>", "LibraryService"))


def test_quote_is_located_by_its_real_lines():
    assert locate_quote(CHUNK, "loan.due = loan.due + 14") == (11, 11)
    assert locate_quote(CHUNK, "def renew(self, loan):\n    loan.due = loan.due + 14") == (10, 11)
    assert locate_quote(CHUNK, "this line is not in the code") is None


def test_an_unauthorised_finding_with_a_real_quote_flags_drift_with_evidence():
    verdict = to_reverse_verdict(_answer(), CHUNK, "c1", "reverse")
    assert verdict.flags_drift and verdict.direction == "reverse"
    assert (verdict.evidence.start_line, verdict.evidence.end_line) == (11, 11)
    assert "No rule authorises: extends a loan" in verdict.violated_clause
    assert verdict.retrieved_chunks == ["svc.py::Svc.renew"]


def test_the_quote_gate_downgrades_findings_it_cannot_verify():
    invented = to_reverse_verdict(_answer(quote="loan.suspend()"), CHUNK, "c1", "reverse")
    assert invented.verdict == "UNCERTAIN" and invented.downgraded
    unexplained = to_reverse_verdict(_answer(behaviour=""), CHUNK, "c1", "reverse")
    assert unexplained.verdict == "UNCERTAIN" and unexplained.downgraded


def test_authorised_and_uncertain_answers_map_through():
    assert to_reverse_verdict({"verdict": "AUTHORISED"}, CHUNK, "c", "r").verdict == "COMPLIANT"
    assert to_reverse_verdict({"verdict": "maybe"}, CHUNK, "c", "r").verdict == "UNCERTAIN"


def test_audit_chunk_caches_on_content(settings, library_dir):
    rules = load_project_rules(library_dir)
    llm = FakeLLM(scripted=[json.dumps(_answer())])
    cache = ResponseCache(settings.cache_dir, namespace="reverse")

    first = audit_chunk(CHUNK, rules, llm, cache, "c1")
    again = audit_chunk(CHUNK, rules, llm, cache, "c2")        # scripted list is empty now
    assert first.flags_drift and not first.cache_hit
    assert again.flags_drift and again.cache_hit
    assert len(llm.calls) == 1


def _build(settings, case_id):
    build_all(settings, case_id=case_id)
    return next(c for c in load_built(settings) if c.case_id == case_id)


def test_reverse_pass_finds_a_planted_operation_and_leaves_the_clean_project_alone(settings):
    detector = build_detector("reverse", settings)

    planted = detector.run_case(_build(settings, "library-D8-01"))
    flagged = [v for v in planted if v.flags_drift]
    assert [v.retrieved_chunks[0].split("::")[-1] for v in flagged] == ["LibraryService.renew"]

    clean = detector.run_case(_build(settings, "library-N1-01"))
    assert not any(v.flags_drift for v in clean)


def test_a_function_already_reported_on_the_pristine_project_is_accepted(settings, library_dir):
    scripted = lambda: FakeLLM(scripted=[])           # noqa: E731 - the heuristic judge is used
    from specdrift.verify.reverse import ReverseChecker

    checker = ReverseChecker(settings, scripted())
    case = _build(settings, "library-N1-01")
    verdicts = checker.audit_workspace(library_dir)
    # Pretend the pristine project's `suspend` was reported: then it must be suppressed in a case.
    suspend = next(v for v in verdicts if v.rule_id == "CREEP:LibraryService.suspend")
    suspend.verdict = "DRIFT"
    chunk = next(c for c in chunk_workspace(library_dir) if c.qualname == "LibraryService.suspend")
    from specdrift.verify.reverse import _digest

    checker._accepted["library"] = {_digest(chunk)}
    flipped = checker.run_case(case)
    assert not any(v.flags_drift for v in flipped)


def _verdict(case_id, direction, qualname, drift=True):
    return Verdict(case_id=case_id, rule_id=f"CREEP:{qualname}", detector="reverse", direction=direction,
                   verdict="DRIFT" if drift else "COMPLIANT", retrieved_chunks=[f"x.py::{qualname}"])


def test_a_reverse_flag_on_the_planted_code_catches_a_d8_case_even_when_it_names_a_rule():
    case = CaseResult(case_id="d8", category="D8", label="drift", status="valid", target_rules=["R09"],
                      gold_symbol="Svc.allow", file="x.py")
    assert case_outcome(case, [_verdict("d8", "reverse", "Svc.allow")])["outcome"] == "TP"
    assert case_outcome(case, [_verdict("d8", "reverse", "Svc.other")])["outcome"] == "FN"


def test_a_reverse_flag_is_spurious_on_other_drift_and_a_false_alarm_on_controls():
    d1 = CaseResult(case_id="d1", category="D1", label="drift", status="valid", target_rules=["R05"],
                    gold_symbol="Svc.refill")
    row = case_outcome(d1, [_verdict("d1", "reverse", "Svc.refill")])
    assert row["outcome"] == "FN" and row["spurious_rules"] == ["CREEP:Svc.refill"]

    control = CaseResult(case_id="n2", category="N2", label="no_drift", status="valid")
    assert case_outcome(control, [_verdict("n2", "reverse", "Svc.refill")])["outcome"] == "FP"
