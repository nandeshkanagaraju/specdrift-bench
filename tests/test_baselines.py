from specdrift.baselines.keyword import key_terms
from specdrift.baselines.wholefile import WholeFileDetector, build_prompt
from specdrift.bench.builder import build_case
from specdrift.bench.schema import CaseSpec, Rule
from specdrift.bench.validator import validate_case
from specdrift.registry import DETECTOR_NAMES, build_detector


def built(settings, case_id, category, label, find="", replace="", file=""):
    case = CaseSpec(
        id=case_id, project="library", category=category, label=label,
        file=file, find=find, replace=replace,
    )
    workspace = build_case(case, settings.projects_dir, settings.work_dir)
    return validate_case(case, workspace)


def test_key_terms_separates_words_from_numbers():
    words, numbers = key_terms("A member MUST NOT hold more than 3 active loans at once.")
    assert "must" not in words
    assert numbers == ["3"]


def test_every_named_detector_can_be_built(settings):
    for name in DETECTOR_NAMES:
        assert build_detector(name, settings).name == name


def test_keyword_emits_one_verdict_per_rule(settings):
    case = built(settings, "kw-1", "N1", "no_drift")
    verdicts = build_detector("keyword", settings).run_case(case)
    assert len(verdicts) == 14
    assert {v.detector for v in verdicts} == {"keyword"}


def test_keyword_is_fooled_by_a_comment_decoy(settings):
    """The check is gone but its comment remains, so the vocabulary still matches."""
    case = built(
        settings, "kw-decoy", "D7", "drift",
        find='        if member.suspended:\n'
             '            raise MemberSuspended(f"member {member_id} is suspended")',
        replace="",
        file="src/library/service.py",
    )
    verdicts = build_detector("keyword", settings).run_case(case)
    r09 = next(v for v in verdicts if v.rule_id == "R09")
    assert r09.verdict == "COMPLIANT"


def test_wholefile_prompt_carries_every_rule_and_file():
    rules = [Rule(id="R01", text="one"), Rule(id="R02", text="two")]
    prompt = build_prompt(rules, [("src/a.py", "code a"), ("src/b.py", "code b")])
    assert prompt.startswith("RULES:")
    assert "R01: one" in prompt and "R02: two" in prompt
    assert "--- src/a.py ---" in prompt and "code b" in prompt


def test_wholefile_indexes_a_list_reply():
    indexed = WholeFileDetector._index('[{"rule_id": "R01", "verdict": "DRIFT"}]')
    assert indexed["R01"]["verdict"] == "DRIFT"


def test_wholefile_tolerates_a_wrapped_list():
    indexed = WholeFileDetector._index('{"rules": [{"rule_id": "R02", "verdict": "COMPLIANT"}]}')
    assert indexed["R02"]["verdict"] == "COMPLIANT"


def test_wholefile_marks_rules_the_model_skipped(settings):
    case = built(settings, "wf-1", "N1", "no_drift")
    detector = build_detector("wholefile", settings)
    detector.llm.scripted = ['[{"rule_id": "R01", "verdict": "COMPLIANT", "confidence": 0.9}]']
    verdicts = detector.run_case(case)

    assert next(v for v in verdicts if v.rule_id == "R01").verdict == "COMPLIANT"
    skipped = next(v for v in verdicts if v.rule_id == "R05")
    assert skipped.verdict == "UNCERTAIN" and skipped.parse_error is True
