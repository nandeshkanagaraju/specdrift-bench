"""The reverse direction: is this code authorised by any rule?

``SpecGuard`` goes rule -> code and asks "does the code still obey this rule?". That can
never see unauthorised scope creep (D8): added behaviour that no rule mentions is, by
construction, similar to no rule, so no rule's retrieval ever surfaces it. This module goes
the other way, code -> rules. For every function and method it shows the model the whole
rule list and asks whether everything the function does is described or presupposed by some
rule.

Two things keep it honest:

* **A quote gate.** An UNAUTHORISED finding must quote, verbatim, the code that implements
  the extra behaviour. A quote that does not appear in the function is not evidence, so the
  finding is downgraded to UNCERTAIN, and the quote's real line numbers become the evidence.
* **An accepted baseline.** Real specifications leave things out (the wallet spec never
  mentions deposits). Run on a codebase as-is, the checker would report that gap on every
  case. As with a static-analysis baseline file, a function that is byte-identical to one
  already reported on the pristine project is treated as accepted, so only *new* behaviour
  is reported.
"""

from __future__ import annotations

import ast
import hashlib
import re
import textwrap
import time
from pathlib import Path

from specdrift.bench.schema import CaseResult, Chunk, Evidence, Rule, Verdict, VerdictValue
from specdrift.cache import ResponseCache
from specdrift.code.chunker import chunk_workspace
from specdrift.config import Settings
from specdrift.spec.parser import load_project_rules
from specdrift.verify.llm import Completer, LLMError, build_llm, with_retries
from specdrift.verify.prompts import render_chunk
from specdrift.verify.verifier import _clamp_confidence, parse_response, uncertain

NAME = "reverse"
REVERSE_PROMPT_VERSION = "rev2"
REVERSE_MARKER = "UNAUTHORISED-BEHAVIOUR CHECK"

SYSTEM_PROMPT = """You audit code for UNAUTHORISED behaviour: behaviour the specification \
does not describe. You are shown every rule of the specification and ONE code excerpt \
(a function or method).

Work in this order. First list in "served_by" the rule ids the excerpt helps to carry out. \
Then decide:

AUTHORISED: the excerpt serves at least one rule and adds nothing the rules do not describe. \
This includes: enforcing a rule or raising the error it names; computing a value a rule \
defines (a fee, a limit, an ordering); recording or reading the data a rule talks about; \
looking an entity up or reporting that it is unknown; constructors, accessors and helpers \
that a rule's behaviour depends on (a rule about suspended members presupposes a way to \
suspend one). A helper that does part of what a rule describes is authorised even though no \
rule names the helper.

UNAUTHORISED: besides anything it serves, the excerpt does something no rule describes or \
presupposes: a new capability, a special case that exempts some callers from a rule, an \
automatic action triggered by a condition no rule states, a pricing or grant rule of its own.

The ABSENCE of a check is never a finding: code that does not validate something has not \
added behaviour. Do not flag style, naming, performance, missing rules, or code that is \
merely odd, and do not judge whether the code obeys a rule. Comments and docstrings are \
claims, not behaviour: judge executable code. A possible risk is not a finding.

If UNAUTHORISED you MUST quote, verbatim, the shortest line(s) of code that carry out the \
extra behaviour, describe that behaviour in one sentence, and name the closest rule or "none".

Return JSON only, with exactly these keys, in this order:
{"served_by": ["R01"],
 "verdict": "AUTHORISED" | "UNAUTHORISED" | "UNCERTAIN",
 "confidence": 0.0-1.0,
 "behaviour": "",
 "quote": "",
 "closest_rule": ""}"""


def build_user_prompt(rules: list[Rule], chunk: Chunk) -> str:
    rule_block = "\n".join(f"{rule.id}: {rule.text}" for rule in rules)
    return (
        f"{REVERSE_MARKER}\n\nSPECIFICATION RULES:\n{rule_block}\n\n"
        f"CODE EXCERPT:\n{render_chunk(chunk)}\n"
    )


# --------------------------------------------------------------------- chunk selection
def is_function_chunk(chunk: Chunk) -> bool:
    """A function or method definition, not a module-constants or class-header chunk."""
    if chunk.qualname == "<module>":
        return False
    try:
        tree = ast.parse(textwrap.dedent(chunk.source))
    except SyntaxError:
        return False
    return bool(tree.body) and isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef))


def reviewable_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Functions and methods worth auditing. Dunder methods only wire up state."""
    return [
        chunk
        for chunk in chunks
        if is_function_chunk(chunk)
        and not (chunk.qualname.rsplit(".", 1)[-1].startswith("__"))
    ]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def locate_quote(chunk: Chunk, quote: str) -> tuple[int, int] | None:
    """Real (start, end) lines of `quote` inside the chunk, or None if it is not there."""
    wanted = [_normalise(line) for line in quote.strip().splitlines() if line.strip()]
    if not wanted:
        return None
    source_lines = [_normalise(line) for line in chunk.source.splitlines()]
    for start in range(len(source_lines) - len(wanted) + 1):
        if all(wanted[i] in source_lines[start + i] for i in range(len(wanted))):
            return chunk.start_line + start, chunk.start_line + start + len(wanted) - 1
    # The model may have joined several lines into one: fall back to a substring match.
    flat = _normalise(chunk.source)
    if _normalise(quote) in flat:
        return chunk.start_line, chunk.end_line
    return None


# --------------------------------------------------------------------- verdict building
def to_reverse_verdict(payload: dict, chunk: Chunk, case_id: str, detector: str) -> Verdict:
    """Map a reverse answer to a Verdict, applying the quote gate to UNAUTHORISED."""
    raw = str(payload.get("verdict", "")).strip().upper()
    behaviour = str(payload.get("behaviour") or "").strip()
    quote = str(payload.get("quote") or "").strip()
    closest = str(payload.get("closest_rule") or "").strip()

    verdict: VerdictValue = (
        "COMPLIANT" if raw == "AUTHORISED" else "DRIFT" if raw == "UNAUTHORISED" else "UNCERTAIN"
    )
    lines = locate_quote(chunk, quote) if quote else None
    downgraded = verdict == "DRIFT" and not (behaviour and lines)
    if downgraded:
        verdict = "UNCERTAIN"

    evidence = Evidence(file=chunk.file)
    if lines and verdict == "DRIFT":
        evidence = Evidence(file=chunk.file, start_line=lines[0], end_line=lines[1])

    clause = ""
    if verdict == "DRIFT":
        clause = f"No rule authorises: {behaviour}"
        if closest and closest.lower() != "none":
            clause += f" (closest rule {closest})"

    return Verdict(
        case_id=case_id,
        rule_id=f"CREEP:{chunk.qualname}",
        detector=detector,
        direction="reverse",
        verdict=verdict,
        confidence=_clamp_confidence(payload.get("confidence", 0.0)),
        violated_clause=clause,
        evidence=evidence,
        retrieved_chunks=[chunk.id],
        downgraded=downgraded,
    )


def audit_chunk(
    chunk: Chunk,
    rules: list[Rule],
    llm: Completer,
    cache: ResponseCache | None,
    case_id: str,
    detector: str = NAME,
    run: int = 1,
) -> Verdict:
    """One model call for one function, cached on the content of the question."""
    user = build_user_prompt(rules, chunk)
    model = getattr(llm, "model", "unknown")
    key = ResponseCache.key(
        "\n".join(rule.text for rule in rules), [chunk.source], model, REVERSE_PROMPT_VERSION, run
    )
    rule_id = f"CREEP:{chunk.qualname}"

    started = time.perf_counter()
    cached = cache.get(key) if cache else None
    response = cached
    if response is None:
        try:
            response = with_retries(llm, SYSTEM_PROMPT, user)
        except LLMError as exc:
            out = uncertain(case_id, rule_id, detector, f"provider error: {exc}")
            out.direction, out.retrieved_chunks = "reverse", [chunk.id]
            return out

    payload = parse_response(response)
    if payload is None and cached is None:
        try:
            response = with_retries(llm, SYSTEM_PROMPT, user)
        except LLMError as exc:
            out = uncertain(case_id, rule_id, detector, f"provider error: {exc}")
            out.direction, out.retrieved_chunks = "reverse", [chunk.id]
            return out
        payload = parse_response(response)

    if payload is None:
        out = uncertain(case_id, rule_id, detector, "model did not return valid JSON")
        out.direction, out.retrieved_chunks = "reverse", [chunk.id]
    else:
        out = to_reverse_verdict(payload, chunk, case_id, detector)
        if cache and cached is None and response is not None:
            cache.put(key, response)

    out.latency_ms = int((time.perf_counter() - started) * 1000)
    out.cache_hit = cached is not None
    out.run = run
    return out


# --------------------------------------------------------------------- the detector
def _digest(chunk: Chunk) -> str:
    return hashlib.sha256(_normalise(chunk.source).encode("utf-8")).hexdigest()


class ReverseChecker:
    """Code -> rules. One verdict per function or method in the workspace."""

    name = NAME

    def __init__(self, settings: Settings, llm: Completer | None = None) -> None:
        self.settings = settings
        self.llm = llm or build_llm(settings)
        self.cache = ResponseCache(settings.cache_dir, namespace="reverse")
        self._accepted: dict[str, set[str]] = {}

    @property
    def model(self) -> str:
        return getattr(self.llm, "model", "unknown")

    def audit_workspace(self, workspace: Path, case_id: str = "live", run: int = 1) -> list[Verdict]:
        rules = load_project_rules(workspace)
        return [
            audit_chunk(chunk, rules, self.llm, self.cache, case_id, self.name, run)
            for chunk in reviewable_chunks(chunk_workspace(workspace))
        ]

    def accepted_baseline(self, project: str, run: int = 1) -> set[str]:
        """Digests of functions already reported on the pristine project (accepted as-is)."""
        if project not in self._accepted:
            pristine = self.settings.projects_dir / project
            digests: set[str] = set()
            if pristine.exists():
                rules = load_project_rules(pristine)
                for chunk in reviewable_chunks(chunk_workspace(pristine)):
                    verdict = audit_chunk(chunk, rules, self.llm, self.cache, "baseline", self.name, run)
                    if verdict.flags_drift:
                        digests.add(_digest(chunk))
            self._accepted[project] = digests
        return self._accepted[project]

    def run_case(self, case: CaseResult, run: int = 1) -> list[Verdict]:
        workspace = Path(case.workspace)
        verdicts = self.audit_workspace(workspace, case.case_id, run)
        if not self.settings.reverse_baseline or not case.project:
            return verdicts

        accepted = self.accepted_baseline(case.project, run)
        by_id = {chunk.id: chunk for chunk in chunk_workspace(workspace)}
        for verdict in verdicts:
            chunk = by_id.get(verdict.retrieved_chunks[0]) if verdict.retrieved_chunks else None
            if verdict.flags_drift and chunk is not None and _digest(chunk) in accepted:
                verdict.verdict = "COMPLIANT"
                verdict.violated_clause = "accepted: already reported on the pristine project"
        return verdicts


class SpecGuardReverse:
    """SpecGuard's rule -> code verdicts plus the reverse pass: both directions."""

    name = "specguard-reverse"

    def __init__(self, settings: Settings, llm: Completer | None = None) -> None:
        from specdrift.verify.engine import SpecGuard

        self.settings = settings
        self.forward = SpecGuard(settings, llm)
        self.reverse = ReverseChecker(settings, self.forward.llm)
        self.cache = _CombinedCache(self.forward.cache, self.reverse.cache)

    @property
    def model(self) -> str:
        return self.forward.model

    def run_case(self, case: CaseResult, run: int = 1) -> list[Verdict]:
        forward = self.forward.run_case(case, run)
        for verdict in forward:
            verdict.detector = self.name
        reverse = self.reverse.run_case(case, run)
        for verdict in reverse:
            verdict.detector = self.name
        return forward + reverse


class _CombinedCache:
    """Hit and miss counts across the forward and reverse caches, for the run statistics."""

    def __init__(self, *caches: ResponseCache) -> None:
        self._caches = caches

    @property
    def hits(self) -> int:
        return sum(c.hits for c in self._caches)

    @property
    def misses(self) -> int:
        return sum(c.misses for c in self._caches)
