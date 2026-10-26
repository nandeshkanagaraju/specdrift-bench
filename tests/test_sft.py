import json

import pytest
from typer.testing import CliRunner

from specdrift import cli
from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule
from specdrift.data.schema import Provenance, Target, TrainingExample
from specdrift.data.sft import KEY_ORDER, check_round_trip, completion_text, export, to_record
from specdrift.verify.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from specdrift.verify.verifier import parse_response

runner = CliRunner()
RULE = Rule(id="R01", text="`f` MUST return x unchanged.", section="f")
CHUNK = Chunk(id="a.py::f", file="a.py", qualname="f", start_line=1, end_line=2,
              source="def f(x):\n    return x + 1\n")


def example(label, *, target=None, split="train", name="e1", project="p1"):
    if target is None:
        if label == "DRIFT":
            target = Target(verdict="DRIFT", confidence=0.9, violated_clause="`f` MUST return x unchanged.",
                            evidence=Evidence(file="a.py", start_line=2, end_line=2),
                            counterexample=Counterexample(input="f(1)", expected="1", actual="2"))
        else:
            target = Target(verdict=label, confidence=0.9)
    return TrainingExample(
        example_id=name, source="synth", split=split, project_id=project, rule=RULE, chunks=[CHUNK],
        label=label, category="D1", target=target,
        provenance=Provenance(label_method="execution", generator="injector-v1"))


def test_prompt_is_exactly_what_serving_builds():
    record = to_record(example("DRIFT"))
    system, user = record["prompt"]
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user == {"role": "user", "content": build_user_prompt(RULE, [CHUNK])}
    assert record["prompt_version"] == PROMPT_VERSION


def test_completion_uses_the_key_order_of_the_system_prompt():
    parsed = json.loads(completion_text(example("DRIFT").target))
    assert tuple(parsed) == KEY_ORDER
    assert completion_text(example("COMPLIANT").target).startswith('{"verdict": "COMPLIANT"')


@pytest.mark.parametrize("label", ["DRIFT", "COMPLIANT", "UNCERTAIN"])
def test_every_label_round_trips_through_the_production_parser(label):
    ex = example(label)
    assert check_round_trip(ex, completion_text(ex.target)) is None
    assert parse_response(to_record(ex)["completion"][0]["content"])["verdict"] == label


def test_a_drift_without_a_counterexample_is_refused():
    bare = Target(verdict="DRIFT", confidence=0.9, violated_clause="`f` MUST return x unchanged.")
    records, refused = export([example("DRIFT", target=bare, name="bad"), example("COMPLIANT", name="good")])
    assert [r["example_id"] for r in records] == ["good"]
    assert refused == [("bad", "a DRIFT target would be downgraded by the evidence bar")]


def test_a_target_that_disagrees_with_its_label_is_refused():
    wrong = example("COMPLIANT", target=Target(verdict="UNCERTAIN"), name="mismatch")
    _, refused = export([wrong])
    assert refused and "labelled COMPLIANT" in refused[0][1]


def test_unparseable_completion_is_refused():
    assert check_round_trip(example("COMPLIANT"), "not json") == "completion is not parseable JSON"


def test_cli_writes_both_splits_and_a_summary(tmp_path):
    mix_dir = tmp_path / "mix"
    mix_dir.mkdir()
    for split in ("train", "val"):
        rows = [example(label, split=split, name=f"{split}-{label}", project=f"proj-{split}") for label in ("DRIFT", "COMPLIANT")]
        (mix_dir / f"{split}.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")

    result = runner.invoke(cli.app, ["data-sft", str(mix_dir), "--out", str(tmp_path / "sft")])

    assert result.exit_code == 0, result.output
    train = [json.loads(line) for line in (tmp_path / "sft" / "train.jsonl").read_text().splitlines()]
    assert {r["label"] for r in train} == {"DRIFT", "COMPLIANT"}
    summary = json.loads((tmp_path / "sft" / "sft.json").read_text())
    assert summary["val"]["examples"] == 2 and summary["val"]["refused"] == 0


def test_cli_exits_nonzero_when_something_is_refused(tmp_path):
    mix_dir = tmp_path / "mix"
    mix_dir.mkdir()
    for split in ("train", "val"):
        bad = example("DRIFT", target=Target(verdict="DRIFT", violated_clause="x"), name="bad",
                      split=split, project=f"proj-{split}")
        (mix_dir / f"{split}.jsonl").write_text(bad.model_dump_json() + "\n", encoding="utf-8")

    result = runner.invoke(cli.app, ["data-sft", str(mix_dir), "--out", str(tmp_path / "sft")])

    assert result.exit_code == 1
    assert "refused bad" in result.output
