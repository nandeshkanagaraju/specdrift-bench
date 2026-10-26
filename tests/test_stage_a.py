import json

import pytest

from specdrift.data import stage_a
from specdrift.data.schema import TrainingExample
from specdrift.data.stage_a import Stats, convert, convert_task

DECL = "def add(a, b):\n"
TEST = "def check(candidate):\n    assert candidate(1, 2) == 3\n    assert candidate(0, 0) == 0\n\ncheck(add)\n"


def row(**over):
    base = {
        "task_id": "Python/1",
        "text": "    Return the sum of a and b. Both are integers.",
        "declaration": DECL,
        "canonical_solution": "    return a + b\n",
        "buggy_solution": "    return a - b\n",
        "test": TEST,
        "bug_type": "operator misuse",
        "failure_symptoms": "incorrect output",
    }
    base.update(over)
    return base


def test_a_real_pair_becomes_one_compliant_and_one_drift_example():
    stats = Stats()
    examples = convert_task("humaneval", row(), stats)
    assert [e.label for e in examples] == ["COMPLIANT", "DRIFT"]

    drift = examples[1]
    assert drift.provenance.label_method == "test_suite"
    assert drift.category == "paper:operator misuse"
    # the counterexample was executed, not written
    # shown under the function's real name, not the test's parameter name ("candidate")
    assert drift.target.counterexample.input == "add(1, 2)"
    assert drift.target.counterexample.expected == "3"
    assert drift.target.counterexample.actual == "-1"
    # evidence points at the changed line of the buggy code; the clause is quoted from the rule
    assert drift.target.evidence.start_line == 2
    assert drift.target.violated_clause in drift.rule.text
    assert drift.rule.text == "Return the sum of a and b. Both are integers."
    assert drift.target.violated_clause == "Return the sum of a and b."


def test_evidence_lines_fall_inside_the_chunk():
    for e in convert_task("humaneval", row(), Stats()):
        chunk = e.chunks[0]
        assert chunk.start_line <= e.target.evidence.start_line or e.label == "COMPLIANT"
        assert e.target.evidence.end_line <= chunk.end_line


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"buggy_solution": "    return a +\n"}, "buggy: does not parse"),
        ({"buggy_solution": "    return  a+b\n"}, "buggy: identical to correct code"),
        ({"buggy_solution": "    return a + b + 0\n"}, "buggy: passes the tests"),
        ({"buggy_solution": "    return undefined_name\n"}, None),
    ],
)
def test_bad_buggy_sides_are_dropped_but_the_correct_side_is_kept(over, reason):
    stats = Stats()
    examples = convert_task("mbpp", row(**over), stats)
    if reason:
        assert [e.label for e in examples] == ["COMPLIANT"]
        assert stats.dropped[reason] == 1
    else:  # a NameError at call time is a genuine test failure and a valid DRIFT example
        assert [e.label for e in examples] == ["COMPLIANT", "DRIFT"]
        assert "raises NameError" in examples[1].target.counterexample.actual


def test_a_task_with_empty_tests_is_dropped_entirely():
    stats = Stats()
    empty = "def check(candidate):\n    pass\n\ncheck(add)\n"
    assert convert_task("quixbugs", row(test=empty), stats) == []
    assert stats.dropped["task: tests are empty"] == 1


def test_a_correct_side_that_fails_its_tests_drops_the_task():
    stats = Stats()
    assert convert_task("mbpp", row(canonical_solution="    return a * b\n"), stats) == []
    assert stats.dropped["task: correct code fails its own tests"] == 1


def test_an_infinite_loop_is_a_failure_not_a_hang():
    stats = Stats()
    looping = row(buggy_solution="    while True:\n        pass\n")
    examples = convert_task("quixbugs", looping, stats)
    assert [e.label for e in examples] == ["COMPLIANT", "DRIFT"]
    assert "raises CallTimeout" in examples[1].target.counterexample.actual


@pytest.mark.parametrize(
    "code",
    [
        "import os\n",
        "from subprocess import run\n",
        "def f():\n    return open('x')\n",
        "def f():\n    return eval('1')\n",
        "def f(x):\n    return x.__class__.__bases__\n",
    ],
)
def test_the_safety_screen_blocks_code_before_it_is_ever_run(code):
    assert stage_a.is_unsafe(code)
    stats = Stats()
    bad = row(canonical_solution="    import os\n    return a + b\n")
    assert convert_task("humaneval", bad, stats) == []
    assert stats.dropped["task: failed the safety screen"] == 1


def test_the_screen_lets_ordinary_code_through():
    assert not stage_a.is_unsafe("import math\nfrom typing import List\ndef f(x: List[int]):\n    return math.sqrt(1)\n")


def test_no_execute_mode_labels_by_pairing_and_never_runs_code():
    stats = Stats()
    examples = convert_task("humaneval", row(), stats, execute=False)
    assert {e.provenance.label_method for e in examples} == {"paper_pairing"}
    assert examples[1].target.counterexample.actual == "incorrect output"


def test_both_sides_of_a_task_always_land_in_the_same_split():
    for n in range(40):
        a, b = convert_task("humaneval", row(task_id=f"Python/{n}"), Stats(), execute=False)
        assert a.split == b.split and a.project_id == b.project_id


def test_the_split_is_roughly_ninety_ten():
    splits = [stage_a.split_for("mbpp", f"Python/{n}") for n in range(2000)]
    assert 0.07 < splits.count("val") / len(splits) < 0.13


def test_convert_writes_valid_jsonl_and_a_stats_file(tmp_path):
    src = tmp_path / "src"
    for name in stage_a.DATASETS:
        (src / "dataset" / name).mkdir(parents=True)
        (src / "dataset" / name / f"{name}.jsonl").write_text(json.dumps(row()) + "\n")
    out = tmp_path / "out" / "stage_a.jsonl"

    stats = convert(src, out)

    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(lines) == 6 and stats.written["mbpp/DRIFT"] == 1
    for line in lines:
        TrainingExample.model_validate(line)
    assert json.loads(out.with_suffix(".stats.json").read_text())["tasks"]["humaneval"] == 1
