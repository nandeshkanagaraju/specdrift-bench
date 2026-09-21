"""Baseline 2: one prompt holding the whole spec and the whole codebase.

No retrieval stage at all, so a missed drift can never be blamed on retrieval. It also
costs one large call per case instead of one small call per rule, which is the trade
the two-stage design is arguing against.
"""

from __future__ import annotations

import json
from pathlib import Path

from specdrift.bench.schema import CaseResult, Verdict
from specdrift.cache import ResponseCache
from specdrift.config import Settings
from specdrift.spec.parser import load_project_rules
from specdrift.verify.llm import LLMError, build_llm, with_retries
from specdrift.verify.verifier import parse_response, to_verdict, uncertain

NAME = "wholefile"
PROMPT_VERSION = "wholefile-v1"

SYSTEM_PROMPT = """You check whether a codebase implements each rule of a specification.
You do not review style, performance, or anything the rules do not state. Do not suggest fixes.

For every rule decide:
- DRIFT only if you can quote the exact rule clause violated AND give a concrete input
  where the code's behaviour differs from what the rule requires.
- COMPLIANT if the code implements the rule, even if it could be written differently.
- UNCERTAIN if the code shown does not contain enough to decide.

A possible risk is not a violation. Comments and docstrings are claims, not behaviour.

Return JSON only: a list with one object per rule, each with exactly these keys:
{"rule_id": "R01", "verdict": "COMPLIANT" | "DRIFT" | "UNCERTAIN", "confidence": 0.0-1.0,
 "violated_clause": "", "counterexample": {"input": "", "expected": "", "actual": ""}}"""


def collect_sources(workspace: Path) -> list[tuple[str, str]]:
    base = workspace / "src"
    if not base.exists():
        base = workspace
    return [
        (path.relative_to(workspace).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted(base.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def build_prompt(rules, sources: list[tuple[str, str]]) -> str:
    rule_block = "\n".join(f"{rule.id}: {rule.text}" for rule in rules)
    code_block = "\n\n".join(f"--- {name} ---\n{body}" for name, body in sources)
    return f"RULES:\n{rule_block}\n\nCODE (the whole project):\n{code_block}\n"


class WholeFileDetector:
    name = NAME

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = build_llm(settings, settings.llm_max_tokens_wholefile)
        self.cache = ResponseCache(settings.cache_dir, namespace="wholefile")

    @property
    def model(self) -> str:
        return getattr(self.llm, "model", "unknown")

    def run_case(self, case: CaseResult, run: int = 1) -> list[Verdict]:
        workspace = Path(case.workspace)
        rules = load_project_rules(workspace)
        sources = collect_sources(workspace)
        user = build_prompt(rules, sources)

        key = ResponseCache.key(
            "\n".join(rule.text for rule in rules),
            [body for _, body in sources],
            self.model,
            PROMPT_VERSION,
            run,
        )
        cached = self.cache.get(key)
        response = cached
        if response is None:
            try:
                response = with_retries(self.llm, SYSTEM_PROMPT, user)
            except LLMError as exc:
                # One unreachable case must not sink a whole benchmark run.
                return [
                    uncertain(case.case_id, rule.id, self.name, f"provider error: {exc}")
                    for rule in rules
                ]
            self.cache.put(key, response)

        by_rule = self._index(response)
        verdicts: list[Verdict] = []
        for rule in rules:
            payload = by_rule.get(rule.id)
            if payload is None:
                verdict = uncertain(
                    case.case_id, rule.id, self.name, "model returned no entry for this rule"
                )
            else:
                verdict = to_verdict(payload, case.case_id, rule.id, self.name)
            verdict.cache_hit = cached is not None
            verdict.run = run
            verdicts.append(verdict)
        return verdicts

    @staticmethod
    def salvage_objects(text: str) -> list[dict]:
        """Pull every complete JSON object out of a truncated array.

        A reply cut off by the token limit still carries valid verdicts for the rules
        it reached. Discarding all of them would report a budget problem as a wall of
        UNCERTAIN, which reads like a model that cannot decide anything.
        """
        objects: list[dict] = []
        depth = 0
        start = -1
        in_string = False
        escaped = False

        for index, character in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue

            if character == '"':
                in_string = True
            elif character == "{":
                if depth == 0:
                    start = index
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        parsed = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        objects.append(parsed)
                    start = -1

        return objects

    @staticmethod
    def _index(response: str) -> dict[str, dict]:
        """The reply should be a list; tolerate a bare object, a wrapped list, or a
        list the token limit cut in half."""
        text = (response or "").strip()
        parsed: object = None
        try:
            parsed = json.loads(text.strip("`").removeprefix("json").strip())
        except json.JSONDecodeError:
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    parsed = None

        if isinstance(parsed, dict):
            parsed = parsed.get("rules") or parsed.get("verdicts") or [parsed]
        if not isinstance(parsed, list):
            single = parse_response(text)
            parsed = [single] if single else []

        # Nothing well formed came back, but a truncated array may still hold answers.
        if not parsed:
            parsed = WholeFileDetector.salvage_objects(text)

        return {
            str(item.get("rule_id")): item
            for item in parsed
            if isinstance(item, dict) and item.get("rule_id")
        }
