"""Parse a project's spec.md into numbered atomic rules.

Authors write rules pre-atomised in one exact shape, so parsing stays deterministic:

    ## Loans
    - **R07** A member MUST NOT hold more than 3 active loans at once.
"""

from __future__ import annotations

import re
from pathlib import Path

from specdrift.bench.schema import Rule

RULE_RE = re.compile(r"^\s*[-*]\s+\*\*(?P<id>R\d+)\*\*\s+(?P<text>.+?)\s*$")
HEADING_RE = re.compile(r"^\s*#{2,}\s+(?P<title>.+?)\s*$")


class DuplicateRuleError(ValueError):
    """Two rules in one spec share an id, so verdicts could not be joined."""


def parse_spec_text(text: str) -> list[Rule]:
    rules: list[Rule] = []
    seen: dict[str, int] = {}
    section = ""

    for lineno, line in enumerate(text.splitlines(), start=1):
        heading = HEADING_RE.match(line)
        if heading:
            section = heading.group("title")
            continue

        match = RULE_RE.match(line)
        if not match:
            continue

        rule_id = match.group("id")
        if rule_id in seen:
            raise DuplicateRuleError(
                f"rule {rule_id} is defined twice (lines {seen[rule_id]} and {lineno})"
            )
        seen[rule_id] = lineno
        rules.append(Rule(id=rule_id, text=match.group("text"), section=section))

    return rules


def parse_spec_file(path: str | Path) -> list[Rule]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no spec at {path}")
    return parse_spec_text(path.read_text(encoding="utf-8"))


def load_project_rules(project_dir: str | Path) -> list[Rule]:
    return parse_spec_file(Path(project_dir) / "spec.md")


def rules_by_id(rules: list[Rule]) -> dict[str, Rule]:
    return {rule.id: rule for rule in rules}
