import json

from specdrift.bench.schema import Chunk, Rule
from specdrift.cache import ResponseCache
from specdrift.verify.llm import FakeLLM
from specdrift.verify.prompts import PROMPT_VERSION, build_user_prompt
from specdrift.verify.verifier import parse_response, to_verdict, verify_rule

RULE = Rule(id="R06", text="A member MUST NOT hold more than 3 active loans at once.")
CHUNK = Chunk(
    id="src/a.py::borrow", file="src/a.py", qualname="borrow",
    start_line=41, end_line=44, source="def borrow(self):\n    if n >= 3:\n        raise X\n",
)

FULL_DRIFT = json.dumps({
    "verdict": "DRIFT", "confidence": 0.82,
    "violated_clause": "MUST NOT hold more than 3 active loans",
    "evidence": {"file": "src/a.py", "start_line": 41, "end_line": 44},
    "counterexample": {"input": "a 4th borrow", "expected": "refused", "actual": "allowed"},
})


def test_parses_plain_json():
    assert parse_response('{"verdict": "DRIFT"}')["verdict"] == "DRIFT"


def test_parses_fenced_json():
    assert parse_response('```json\n{"verdict": "COMPLIANT"}\n```')["verdict"] == "COMPLIANT"


def test_parses_json_after_preamble():
    assert parse_response('Sure!\n{"verdict": "UNCERTAIN"}')["verdict"] == "UNCERTAIN"


def test_unparseable_text_returns_none():
    assert parse_response("no json here") is None


def test_unknown_verdict_becomes_uncertain():
    assert to_verdict({"verdict": "MAYBE"}, "c", "R01", "d").verdict == "UNCERTAIN"


def test_drift_without_clause_is_downgraded():
    payload = {"verdict": "DRIFT", "counterexample": {"input": "i", "actual": "a"}}
    assert to_verdict(payload, "c", "R01", "d").verdict == "UNCERTAIN"


def test_drift_without_counterexample_is_downgraded():
    payload = {"verdict": "DRIFT", "violated_clause": "the clause"}
    assert to_verdict(payload, "c", "R01", "d").verdict == "UNCERTAIN"


def test_fully_evidenced_drift_survives():
    verdict = to_verdict(json.loads(FULL_DRIFT), "c", "R06", "specguard")
    assert verdict.verdict == "DRIFT"
    assert verdict.evidence.start_line == 41
    assert verdict.counterexample.expected == "refused"


def test_confidence_is_clamped():
    assert to_verdict({"verdict": "COMPLIANT", "confidence": 7}, "c", "R", "d").confidence == 1.0
    assert to_verdict({"verdict": "COMPLIANT", "confidence": "x"}, "c", "R", "d").confidence == 0.0


def test_prompt_shows_real_line_numbers():
    prompt = build_user_prompt(RULE, [CHUNK])
    assert "  41 |" in prompt
    assert "RULE R06:" in prompt


def test_invalid_json_is_retried_once_then_uncertain():
    llm = FakeLLM(scripted=["not json", "still not json"])
    verdict = verify_rule(RULE, [CHUNK], llm, None, "case-1")
    assert verdict.verdict == "UNCERTAIN"
    assert verdict.parse_error is True
    assert len(llm.calls) == 2


def test_retry_can_recover():
    llm = FakeLLM(scripted=["oops", FULL_DRIFT])
    assert verify_rule(RULE, [CHUNK], llm, None, "case-1").verdict == "DRIFT"


def test_verdict_records_the_retrieved_chunks():
    llm = FakeLLM(scripted=[FULL_DRIFT])
    verdict = verify_rule(RULE, [CHUNK], llm, None, "case-1")
    assert verdict.retrieved_chunks == ["src/a.py::borrow"]


def test_second_call_hits_the_cache(tmp_path):
    cache = ResponseCache(tmp_path)
    first = verify_rule(RULE, [CHUNK], FakeLLM(scripted=[FULL_DRIFT]), cache, "c1")
    second = verify_rule(RULE, [CHUNK], FakeLLM(scripted=[]), cache, "c2")
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.verdict == "DRIFT"


def test_cache_key_depends_on_rule_chunks_model_and_prompt_version():
    base = ResponseCache.key("rule", ["code"], "m", PROMPT_VERSION)
    assert base != ResponseCache.key("other rule", ["code"], "m", PROMPT_VERSION)
    assert base != ResponseCache.key("rule", ["other code"], "m", PROMPT_VERSION)
    assert base != ResponseCache.key("rule", ["code"], "other", PROMPT_VERSION)
    assert base != ResponseCache.key("rule", ["code"], "m", "v2")


def test_run_salt_bypasses_the_cache():
    base = ResponseCache.key("rule", ["code"], "m", PROMPT_VERSION, run=1)
    assert base != ResponseCache.key("rule", ["code"], "m", PROMPT_VERSION, run=2)


def test_fake_llm_never_touches_the_network():
    llm = FakeLLM()
    reply = llm.complete("sys", build_user_prompt(RULE, [CHUNK]))
    assert json.loads(reply)["verdict"] in {"COMPLIANT", "DRIFT", "UNCERTAIN"}
