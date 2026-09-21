"""Baseline 1: does the rule's vocabulary appear anywhere in the code?

Deliberately naive. It reads comments and docstrings as if they were behaviour, which
is exactly what a comment decoy (D7) exploits, and it has no way at all to see drift
that adds behaviour (D8). It is here to show what a cheap check buys.
"""

from __future__ import annotations

from pathlib import Path

from specdrift.bench.schema import CaseResult, Counterexample, Verdict
from specdrift.config import Settings
from specdrift.retrieval.embedder import tokenize
from specdrift.spec.parser import load_project_rules

MATCH_THRESHOLD = 0.60
NAME = "keyword"

# Words that carry obligation rather than meaning; every rule has them.
MODALS = frozenset({"must", "shall", "should", "may", "mustnot", "required"})


def key_terms(rule_text: str) -> tuple[list[str], list[str]]:
    """Split a rule into its content words and the literal numbers it states."""
    tokens = tokenize(rule_text)
    words = [token for token in tokens if not token[0].isdigit() and token not in MODALS]
    numbers = [token for token in tokens if token[0].isdigit()]
    return words, numbers


def source_text(workspace: Path) -> str:
    """Every line of Python in the workspace, comments included.

    Comments are deliberately in scope: the design document specifies this baseline
    searches all source text, and reading comments as if they were behaviour is the
    weakness a comment decoy (D7) is built to expose. One side effect is worth knowing
    when reading its numbers: a rule-id annotation such as ``# R12`` tokenises to the
    value 12, so a rule that states 12 can look satisfied by its own cross-reference.
    """
    base = workspace / "src"
    if not base.exists():
        base = workspace
    parts = [
        path.read_text(encoding="utf-8")
        for path in sorted(base.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]
    return "\n".join(parts)


class KeywordDetector:
    name = NAME
    model = "n/a"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run_case(self, case: CaseResult, run: int = 1) -> list[Verdict]:
        workspace = Path(case.workspace)
        rules = load_project_rules(workspace)
        haystack = source_text(workspace)
        haystack_tokens = set(tokenize(haystack))
        haystack_numbers = {token for token in haystack_tokens if token[0].isdigit()}

        verdicts: list[Verdict] = []
        for rule in rules:
            words, numbers = key_terms(rule.text)
            matched = [word for word in words if word in haystack_tokens]
            missing_numbers = [n for n in numbers if n not in haystack_numbers]
            fraction = len(matched) / len(words) if words else 1.0

            compliant = fraction >= MATCH_THRESHOLD and not missing_numbers
            if compliant:
                verdicts.append(
                    Verdict(
                        case_id=case.case_id, rule_id=rule.id, detector=self.name,
                        verdict="COMPLIANT", confidence=round(fraction, 3), run=run,
                    )
                )
                continue

            reason = (
                f"value {missing_numbers[0]} from the rule appears nowhere in the code"
                if missing_numbers
                else f"only {fraction:.0%} of the rule's terms appear in the code"
            )
            verdicts.append(
                Verdict(
                    case_id=case.case_id, rule_id=rule.id, detector=self.name,
                    verdict="DRIFT", confidence=round(1.0 - fraction, 3),
                    violated_clause=rule.text[:160],
                    counterexample=Counterexample(
                        input="the rule's own vocabulary",
                        expected="every term and number of the rule appears in the code",
                        actual=reason,
                    ),
                    run=run,
                )
            )
        return verdicts
