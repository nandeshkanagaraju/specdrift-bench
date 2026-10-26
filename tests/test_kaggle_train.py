import importlib.util

from specdrift.config import REPO_ROOT

spec = importlib.util.spec_from_file_location("kaggle_train_qlora", REPO_ROOT / "scripts" / "kaggle_train_qlora.py")
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)


class Tok:
    """One id per character, so lengths are easy to reason about."""
    eos_token = "<eos>"

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize is False and add_generation_prompt is True
        return "".join(m["content"] for m in messages) + "<assistant>"

    def __call__(self, text, add_special_tokens):
        assert add_special_tokens is False
        return {"input_ids": [ord(c) for c in text]}


RECORD = {"prompt": [{"role": "user", "content": "ab"}], "completion": [{"role": "assistant", "content": "xy"}]}


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
