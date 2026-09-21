import pytest

from specdrift.spec.parser import DuplicateRuleError, parse_spec_text, rules_by_id

SPEC = """
# Title

Prose that is not a rule.

## Loans

- **R07** A member MUST NOT hold more than 3 active loans at once.
- **R08** Borrowing MUST fail with `LoanLimitExceeded`.

## Fees

* **R09** The late fee MUST be 0.50 per day.
- not a rule at all
"""


def test_parses_every_numbered_rule():
    rules = parse_spec_text(SPEC)
    assert [rule.id for rule in rules] == ["R07", "R08", "R09"]


def test_carries_the_nearest_heading_as_section():
    rules = rules_by_id(parse_spec_text(SPEC))
    assert rules["R07"].section == "Loans"
    assert rules["R09"].section == "Fees"


def test_ignores_prose_and_unnumbered_bullets():
    assert len(parse_spec_text(SPEC)) == 3


def test_duplicate_rule_ids_are_rejected():
    with pytest.raises(DuplicateRuleError):
        parse_spec_text("- **R01** one\n- **R01** two\n")


def test_every_host_project_spec_parses(settings):
    for project in ("library", "wallet", "ratelimiter"):
        rules = parse_spec_text((settings.projects_dir / project / "spec.md").read_text())
        assert 10 <= len(rules) <= 14, f"{project} has {len(rules)} rules"
        assert len({rule.id for rule in rules}) == len(rules)
