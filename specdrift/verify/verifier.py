"""Stage 2 - ask the model about one rule, then hold its answer to the evidence bar."""

from __future__ import annotations

import json
import re
import time

from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule, Verdict
from specdrift.cache import ResponseCache
from specdrift.verify.llm import Completer, LLMError
from specdrift.verify.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
VALID_VERDICTS = {"COMPLIANT", "DRIFT", "UNCERTAIN"}


def parse_response(text: str) -> dict | None:
    """Pull a JSON object out of a model reply, tolerating code fences and preamble."""
    cleaned = _FENCE_RE.sub("", text or "").strip()
    if not cleaned:
        return None

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = _OBJECT_RE.search(cleaned)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None


def _clamp_confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))       # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def to_verdict(payload: dict, case_id: str, rule_id: str, detector: str) -> Verdict:
    """Build a Verdict, applying the evidence bar that a DRIFT claim has to clear."""
    raw = str(payload.get("verdict", "")).strip().upper()
    verdict = raw if raw in VALID_VERDICTS else "UNCERTAIN"

    clause = str(payload.get("violated_clause") or "").strip()
    evidence_raw = payload.get("evidence") or {}
    counter_raw = payload.get("counterexample") or {}

    evidence = Evidence(
        file=str(evidence_raw.get("file") or ""),
        start_line=int(evidence_raw.get("start_line") or 0),
        end_line=int(evidence_raw.get("end_line") or 0),
    )
    counterexample = Counterexample(
        input=str(counter_raw.get("input") or "").strip(),
        expected=str(counter_raw.get("expected") or "").strip(),
        actual=str(counter_raw.get("actual") or "").strip(),
    )

    # An unsupported drift claim is the dominant false-alarm mode in the literature,
    # so a DRIFT without both a quoted clause and a counterexample is not accepted.
    has_counterexample = bool(counterexample.input and counterexample.actual)
    if verdict == "DRIFT" and not (clause and has_counterexample):
        verdict = "UNCERTAIN"

    return Verdict(
        case_id=case_id,
        rule_id=rule_id,
        detector=detector,
        verdict=verdict,
        confidence=_clamp_confidence(payload.get("confidence", 0.0)),
        violated_clause=clause,
        evidence=evidence,
        counterexample=counterexample,
    )


def uncertain(case_id: str, rule_id: str, detector: str, reason: str) -> Verdict:
    return Verdict(
        case_id=case_id,
        rule_id=rule_id,
        detector=detector,
        verdict="UNCERTAIN",
        confidence=0.0,
        violated_clause=reason,
        parse_error=True,
    )


def verify_rule(
    rule: Rule,
    chunks: list[Chunk],
    llm: Completer,
    cache: ResponseCache | None,
    case_id: str,
    detector: str = "specguard",
    run: int = 1,
) -> Verdict:
    """One model call for one rule, cached on the content of the question."""
    user = build_user_prompt(rule, chunks)
    model = getattr(llm, "model", "unknown")
    key = ResponseCache.key(rule.text, [c.source for c in chunks], model, PROMPT_VERSION, run)

    started = time.perf_counter()
    cached = cache.get(key) if cache else None
    response = cached

    if response is None:
        try:
            response = llm.complete(SYSTEM_PROMPT, user)
        except LLMError as exc:
            return uncertain(case_id, rule.id, detector, f"provider error: {exc}")

    payload = parse_response(response)
    if payload is None and cached is None:
        # One retry, exactly as the design document specifies, then give up.
        try:
            response = llm.complete(SYSTEM_PROMPT, user)
        except LLMError as exc:
            return uncertain(case_id, rule.id, detector, f"provider error: {exc}")
        payload = parse_response(response)

    latency_ms = int((time.perf_counter() - started) * 1000)

    if payload is None:
        verdict = uncertain(case_id, rule.id, detector, "model did not return valid JSON")
    else:
        verdict = to_verdict(payload, case_id, rule.id, detector)
        if cache and cached is None and response is not None:
            cache.put(key, response)

    verdict.retrieved_chunks = [chunk.id for chunk in chunks]
    verdict.latency_ms = latency_ms
    verdict.cache_hit = cached is not None
    verdict.run = run
    return verdict
