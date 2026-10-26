import json

import pytest
from typer.testing import CliRunner

from specdrift import cli
from specdrift.bench.schema import Chunk, Counterexample, Evidence, Rule
from specdrift.config import REPO_ROOT
from specdrift.data.leakage import load_examples
from specdrift.data.schema import Provenance, Target, TrainingExample
from specdrift.data.sft import (
    KEY_ORDER,
    check_round_trip,
    completion_text,
    estimate_tokens,
    export,
    summarise,
    to_records,
)
from specdrift.data.validate import MAX_TOKENS
from specdrift.verify.llm import FakeLLM
from specdrift.verify.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from specdrift.verify.verifier import parse_response, verify_rule

runner = CliRunner()
RULE = Rule(id="R01", text="`f` MUST return x unchanged.", section="f")
CHUNK = Chunk(id="a.py::f", file="a.py", qualname="f", start_line=1, end_line=2,
              source="def f(x):\n    return x + 1\n")
PILOT = REPO_ROOT / "data" / "mix" / "pilot-v1"


def example(label, *, target=None, split="train", name="e1", project="p1", chunk=CHUNK, notes=None,
            category="D1"):
    if target is None:
        if label == "DRIFT":
            target = Target(verdict="DRIFT", confidence=0.9, violated_clause="`f` MUST return x unchanged.",
                            evidence=Evidence(file="a.py", start_line=2, end_line=2),
                            counterexample=Counterexample(input="f(1)", expected="1", actual="2"))
        else:
            target = Target(verdict=label, confidence=0.9)
    return TrainingExample(
        example_id=name, source="synth", split=split, project_id=project, rule=RULE, chunks=[chunk],
        label=label, category=category, target=target,
        provenance=Provenance(label_method="execution", generator="injector-v1", notes=notes or {}))


def test_chat_record_is_system_user_assistant_built_by_the_serving_code():
    chat, plain, _ = to_records(example("DRIFT"))
    system, user, assistant = chat["messages"]
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user == {"role": "user", "content": build_user_prompt(RULE, [CHUNK])}
    assert assistant["role"] == "assistant"
    assert plain == {"example_id": "e1", "system": SYSTEM_PROMPT, "prompt": user["content"],
                     "completion": assistant["content"]}


def test_completion_uses_the_key_order_of_the_system_prompt():
    parsed = json.loads(completion_text(example("DRIFT").target))
    assert tuple(parsed) == KEY_ORDER
    assert set(parsed["evidence"]) == {"file", "start_line", "end_line"}
    assert set(parsed["counterexample"]) == {"input", "expected", "actual"}


@pytest.mark.parametrize("label", ["DRIFT", "COMPLIANT", "UNCERTAIN"])
def test_every_label_round_trips_through_the_production_parser(label):
    ex = example(label)
    assert check_round_trip(ex, completion_text(ex.target)) is None
    assert parse_response(to_records(ex)[0]["messages"][2]["content"])["verdict"] == label


def test_a_drift_without_a_counterexample_is_refused():
    bare = Target(verdict="DRIFT", confidence=0.9, violated_clause="`f` MUST return x unchanged.")
    kept, refused = export([example("DRIFT", target=bare, name="bad"), example("COMPLIANT", name="good")])
    assert [c["example_id"] for c, _, _ in kept] == ["good"]
    assert refused == [("bad", "a DRIFT target would be downgraded by the evidence bar")]


def test_a_target_that_disagrees_with_its_label_is_refused():
    wrong = example("COMPLIANT", target=Target(verdict="UNCERTAIN"), name="mismatch")
    _, refused = export([wrong])
    assert refused and "labelled COMPLIANT" in refused[0][1]


def test_unparseable_completion_is_refused():
    assert check_round_trip(example("COMPLIANT"), "not json") == "completion is not parseable JSON"


def test_no_train_serve_skew_the_sft_prompt_is_what_verify_rule_sends():
    ex = example("COMPLIANT")
    chat, _, _ = to_records(ex)
    llm = FakeLLM(scripted=[chat["messages"][2]["content"]])

    verdict = verify_rule(RULE, [CHUNK], llm, cache=None, case_id="c1")

    assert llm.calls == [(chat["messages"][0]["content"], chat["messages"][1]["content"])]
    assert verdict.verdict == "COMPLIANT" and not verdict.downgraded and not verdict.parse_error


def test_nothing_about_the_label_or_provenance_reaches_the_prompt_or_the_training_records():
    notes = {"operator": "zz_operator_zz", "mutant_id": "zz_mutant_zz", "inject_find": "zz_find_zz"}
    ex = example("DRIFT", name="zz_example_zz", project="zz_project_zz", category="zz_category_zz", notes=notes)
    chat, plain, index = to_records(ex)

    text = json.dumps([chat, plain])
    for secret in ("zz_operator_zz", "zz_mutant_zz", "zz_find_zz", "zz_project_zz", "zz_category_zz"):
        assert secret not in text
    assert set(chat) == {"example_id", "messages"} and set(plain) == {"example_id", "system", "prompt", "completion"}
    # ... while the index, which the model never sees, does carry them.
    assert index["category"] == "zz_category_zz" and index["operator"] == "zz_operator_zz"
    assert index["label"] == "DRIFT" and index["prompt_version"] == PROMPT_VERSION


def test_summary_counts_labels_categories_and_the_share_over_the_token_limit():
    def with_lines(n):
        return Chunk(id="a.py::f", file="a.py", qualname="f", start_line=1, end_line=n,
                     source="x = 1\n" * n)

    # Find the smallest chunk that crosses the limit, so "just over" and "just under" are both tested.
    n = 1
    while True:
        probe = example("COMPLIANT", chunk=with_lines(n))
        if estimate_tokens(probe, completion_text(probe.target)) > MAX_TOKENS:
            break
        n += 1
    over, under = with_lines(n), with_lines(n - 1)
    kept, _ = export([example("COMPLIANT", name="a", category="N1"), example("DRIFT", name="b"),
                      example("COMPLIANT", name="c", category="N1", chunk=over),
                      example("COMPLIANT", name="d", category="N1", chunk=under)])
    info = summarise(kept, refused=0)

    assert info["examples"] == 4 and info["labels"] == {"COMPLIANT": 3, "DRIFT": 1}
    assert info["categories"] == {"D1": 1, "N1": 3}
    assert info["over_limit"] == {"limit": MAX_TOKENS, "count": 1, "share": 0.25}
    assert info["approx_tokens"]["max"] > MAX_TOKENS >= sorted(
        i["approx_tokens"] for _, _, i in kept)[-2]


@pytest.mark.skipif(not (PILOT / "train.jsonl").exists(), reason="pilot mix not built (data/ is local only)")
def test_every_example_in_the_pilot_mix_round_trips_without_a_downgrade_and_matches_serving():
    examples = load_examples([PILOT / "train.jsonl", PILOT / "val.jsonl"])
    assert len(examples) >= 500
    kept, refused = export(examples)
    assert refused == [] and len(kept) == len(examples)

    for ex, (chat, _, _) in zip(examples, kept, strict=True):
        llm = FakeLLM(scripted=[chat["messages"][2]["content"]])
        verdict = verify_rule(ex.rule, ex.chunks, llm, cache=None, case_id=ex.example_id)
        assert llm.calls == [(SYSTEM_PROMPT, chat["messages"][1]["content"])], ex.example_id
        assert verdict.verdict == ex.label and not verdict.downgraded, ex.example_id


def _write_mix(tmp_path):
    mix_dir = tmp_path / "mix"
    mix_dir.mkdir()
    for split in ("train", "val"):
        rows = [example(label, split=split, name=f"{split}-{label}", project=f"proj-{split}") for label in
                ("DRIFT", "COMPLIANT")]
        (mix_dir / f"{split}.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    return mix_dir


def test_cli_writes_three_files_per_split_and_a_stats_file(tmp_path):
    result = runner.invoke(cli.app, ["data-sft", str(_write_mix(tmp_path)), "--out", str(tmp_path / "sft")])

    assert result.exit_code == 0, result.output
    out = tmp_path / "sft"
    for split in ("train", "val"):
        for suffix in ("chat.jsonl", "jsonl", "index.jsonl"):
            assert (out / f"{split}.{suffix}").is_file()
    chat = [json.loads(line) for line in (out / "train.chat.jsonl").read_text().splitlines()]
    index = [json.loads(line) for line in (out / "train.index.jsonl").read_text().splitlines()]
    assert [c["example_id"] for c in chat] == [i["example_id"] for i in index]
    assert {i["label"] for i in index} == {"DRIFT", "COMPLIANT"}
    stats = json.loads((out / "sft.json").read_text())
    assert stats["prompt_version"] == PROMPT_VERSION
    assert "completion" in stats["loss"] and "estimate" in stats["token_method"]
    assert stats["val"]["examples"] == 2 and stats["val"]["refused"] == 0
    assert "completion (assistant message) only" in result.output


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
