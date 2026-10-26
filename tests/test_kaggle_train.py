import importlib.util
import json
import re
import sys
import types

import pytest

from specdrift.config import REPO_ROOT
from specdrift.verify.verifier import parse_response, to_verdict

SCRIPT = REPO_ROOT / "scripts" / "kaggle" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("kaggle_train_qlora", SCRIPT)
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)        # importing must not need torch, transformers or peft


class Tok:
    """One id per character, so lengths are easy to reason about."""
    eos_token = "<eos>"

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize is False and add_generation_prompt is True
        return "".join(m["content"] for m in messages) + "<assistant>"

    def __call__(self, text, add_special_tokens):
        assert add_special_tokens is False
        return {"input_ids": [ord(c) for c in text]}


RECORD = {"messages": [{"role": "user", "content": "ab"}, {"role": "assistant", "content": "xy"}]}


def test_loss_covers_only_the_completion_and_the_end_token():
    encoded = train.encode_example(Tok(), RECORD, max_len=100)
    prompt_len = len("ab<assistant>")
    assert encoded["labels"][:prompt_len] == [train.IGNORE] * prompt_len
    assert encoded["labels"][prompt_len:] == [ord(c) for c in "xy<eos>"]
    assert len(encoded["input_ids"]) == len(encoded["labels"])
    assert encoded["input_ids"][prompt_len:] == encoded["labels"][prompt_len:]


def test_an_example_over_the_limit_is_dropped_not_truncated():
    assert train.encode_example(Tok(), RECORD, max_len=5) is None
    kept, dropped = train.encode_all(Tok(), [RECORD, RECORD], max_len=5)
    assert kept == [] and dropped == 2


def test_a_record_not_ending_in_the_assistant_is_an_error():
    with pytest.raises(ValueError, match="not the assistant"):
        train.encode_example(Tok(), {"messages": [{"role": "user", "content": "a"}]}, max_len=100)


def test_padding_is_masked_out_of_loss_and_attention():
    short = {"input_ids": [1, 2], "labels": [train.IGNORE, 2]}
    long = {"input_ids": [1, 2, 3, 4], "labels": [train.IGNORE, 2, 3, 4]}
    batch = train.pad_batch([short, long], pad_id=0)
    assert batch["input_ids"][0] == [1, 2, 0, 0]
    assert batch["labels"][0] == [train.IGNORE, 2, train.IGNORE, train.IGNORE]
    assert batch["attention_mask"] == [[1, 1, 0, 0], [1, 1, 1, 1]]


def test_limit_samples_reproducibly(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("".join(f'{{"n": {i}}}\n' for i in range(50)), encoding="utf-8")
    first = train.load_records(path, 10, seed=17)
    assert first == train.load_records(path, 10, seed=17) and len(first) == 10
    assert len(train.load_records(path, 0, seed=17)) == 50


# --- the gate ---------------------------------------------------------------------------------

DRIFT = ('{"verdict": "DRIFT", "confidence": 0.9, "violated_clause": "f MUST x", "evidence": {"file": "a.py", '
         '"start_line": 1, "end_line": 1}, "counterexample": {"input": "f(1)", "expected": "1", "actual": "2"}}')
CORPUS = [
    DRIFT,
    "```json\n" + DRIFT + "\n```",
    "Sure! Here is my answer:\n" + DRIFT + "\nHope that helps.",
    DRIFT.replace('"violated_clause": "f MUST x"', '"violated_clause": ""'),
    DRIFT.replace('"input": "f(1)"', '"input": "  "'),
    DRIFT.replace('"actual": "2"', '"actual": ""'),
    DRIFT.replace("DRIFT", "drift"),
    DRIFT.replace('"DRIFT"', '"MAYBE"'),
    '{"verdict": "COMPLIANT", "confidence": 0.9}',
    '{"verdict": "UNCERTAIN"}',
    '{"verdict": "COMPLIANT"} trailing {"verdict": "DRIFT"}',
    "[1, 2, 3]", "not json at all", "", "{", '{"verdict": null}',
]


def production_verdict(text):
    payload = parse_response(text)
    return "UNCERTAIN" if payload is None else to_verdict(payload, "c", "R01", "x").verdict


@pytest.mark.parametrize("text", CORPUS)
def test_the_scripts_verdict_reader_equals_the_production_verifier(text):
    assert train.answer_verdict(text) == production_verdict(text)


def test_the_scripts_verdict_reader_equals_production_on_every_pilot_completion():
    path = REPO_ROOT / "data" / "mix" / "pilot-v1" / "sft" / "train.chat.jsonl"
    if not path.exists():
        pytest.skip("pilot export not built (data/ is local only)")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) > 300
    for row in rows:
        completion = row["messages"][-1]["content"]
        assert train.answer_verdict(completion) == production_verdict(completion), row["example_id"]


def test_gate_metrics_ignore_uncertain_labelled_examples():
    labels = ["COMPLIANT", "COMPLIANT", "COMPLIANT", "COMPLIANT", "DRIFT", "DRIFT", "UNCERTAIN", "UNCERTAIN"]
    preds = ["DRIFT", "COMPLIANT", "COMPLIANT", "UNCERTAIN", "DRIFT", "COMPLIANT", "DRIFT", "COMPLIANT"]
    metrics = train.gate_metrics(labels, preds)
    assert metrics["negatives"] == 4 and metrics["false_alarms"] == 1 and metrics["false_alarm_rate"] == 0.25
    assert metrics["positives"] == 2 and metrics["caught"] == 1 and metrics["recall"] == 0.5
    assert metrics["uncertain_rate"] == round(1 / 6, 4)


def side(fa, recall, negatives=100):
    return {"negatives": negatives, "false_alarm_rate": fa, "recall": recall}


def test_go_only_when_false_alarms_fall_and_recall_holds():
    gate = train.decide_gate(side(0.60, 0.50), side(0.20, 0.50))
    assert gate["decision"] == "GO" and gate["reasons"] == []


def test_equal_false_alarm_rate_is_not_a_go():
    gate = train.decide_gate(side(0.30, 0.50), side(0.30, 0.60))
    assert gate["decision"] == "NO_GO" and "did not fall" in gate["reasons"][0]


def test_a_model_that_stops_flagging_anything_is_not_a_go():
    gate = train.decide_gate(side(0.60, 0.50), side(0.0, 0.0))
    assert gate["decision"] == "NO_GO" and "recall fell" in gate["reasons"][0]
    assert train.decide_gate(side(0.60, 0.50), side(0.0, 0.0), max_recall_drop=1.0)["decision"] == "GO"


def test_too_few_clean_validation_examples_is_not_a_go():
    gate = train.decide_gate(side(0.60, 0.50, negatives=10), side(0.1, 0.5, negatives=10))
    assert gate["decision"] == "NO_GO" and "only 10 clean" in gate["reasons"][0]


def test_7b_is_refused_without_a_go_from_a_1_5b_run(tmp_path):
    train.require_go("Qwen/Qwen2.5-Coder-1.5B-Instruct", None)            # the pilot itself needs no gate
    with pytest.raises(SystemExit, match="needs --go-file"):
        train.require_go("Qwen/Qwen2.5-Coder-7B-Instruct", None)
    with pytest.raises(SystemExit, match="needs --go-file"):
        train.require_go("Qwen/Qwen2.5-Coder-7B-Instruct", str(tmp_path / "missing.json"))

    nogo = tmp_path / "nogo.json"
    nogo.write_text(json.dumps({"decision": "NO_GO", "base": "Qwen/Qwen2.5-Coder-1.5B-Instruct"}))
    with pytest.raises(SystemExit, match="NO_GO"):
        train.require_go("Qwen/Qwen2.5-Coder-7B-Instruct", str(nogo))

    wrong_base = tmp_path / "wrong.json"
    wrong_base.write_text(json.dumps({"decision": "GO", "base": "Qwen/Qwen2.5-Coder-7B-Instruct"}))
    with pytest.raises(SystemExit):
        train.require_go("Qwen/Qwen2.5-Coder-7B-Instruct", str(wrong_base))

    go = tmp_path / "go.json"
    go.write_text(json.dumps({"decision": "GO", "base": "Qwen/Qwen2.5-Coder-1.5B-Instruct"}))
    train.require_go("Qwen/Qwen2.5-Coder-7B-Instruct", str(go))


def test_the_gate_runs_on_gate_data_when_given_so_every_arm_can_share_one_validation_set():
    args = train.build_parser().parse_args(["--data", "/d/arm", "--out", "/o"])
    assert str(train.gate_dir(args)) == "/d/arm"
    args = train.build_parser().parse_args(["--data", "/d/arm", "--out", "/o", "--gate-data", "/d/main"])
    assert str(train.gate_dir(args)) == "/d/main"


def test_unparseable_rate_counts_answers_with_no_json_object():
    assert train.unparseable_rate([DRIFT, "```json\n" + DRIFT + "\n```", "no json", "", "[1]"]) == 0.6
    assert train.unparseable_rate([]) == 0.0


def test_a_zero_false_alarm_baseline_is_called_out_as_a_floor_effect_not_just_no_improvement():
    gate = train.decide_gate(side(0.0, 0.0), side(0.0, 0.0))
    assert gate["decision"] == "NO_GO"
    assert any("raised no false alarm at all" in r and "unparseable" in r for r in gate["reasons"])
    quiet = train.decide_gate(side(0.5, 0.5), side(0.5, 0.5))
    assert not any("raised no false alarm" in r for r in quiet["reasons"])


def test_the_notebooks_default_max_len_is_the_data_validators_limit():
    # The notebook is uploaded on its own and cannot import specdrift, so this test is what keeps the two equal.
    from specdrift.data.validate import MAX_TOKENS

    args = train.build_parser().parse_args(["--data", "d", "--out", "o"])
    assert args.max_len == MAX_TOKENS == 3072


# --- secrets ----------------------------------------------------------------------------------

def test_secrets_come_only_from_kaggle_secrets(monkeypatch):
    monkeypatch.setitem(sys.modules, "kaggle_secrets", None)               # not on Kaggle
    assert train.get_secret("HF_TOKEN") is None

    asked = []

    class Client:
        def get_secret(self, name):
            asked.append(name)
            return "value-from-kaggle"

    monkeypatch.setitem(sys.modules, "kaggle_secrets", types.SimpleNamespace(UserSecretsClient=Client))
    assert train.get_secret("HF_TOKEN") == "value-from-kaggle" and asked == ["HF_TOKEN"]


def test_the_notebook_has_no_secret_in_it_and_takes_none_on_the_command_line():
    text = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}", text)
    options = {a for action in train.build_parser()._actions for a in action.option_strings}
    assert not {o for o in options if re.search(r"token|key|secret|password", o)}
    assert "os.environ" not in text and "getenv" not in text
