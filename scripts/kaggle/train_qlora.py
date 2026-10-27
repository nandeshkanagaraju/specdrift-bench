# %% [markdown]
# # SpecGuard Stage 2: QLoRA fine-tune plus the pilot go/no-go gate
#
# Plain-script notebook (`# %%` cells; open in Kaggle via Jupytext or paste cell by cell). Not run here.
# Upload as a private dataset: this file, and the `sft/` folder from `specdrift data-sft`
# (train.chat.jsonl, val.chat.jsonl, val.index.jsonl).
#
# Order of work (docs/training-data-spec.md, sections 9 and 11):
#   1. 1.5B pilot:  python train_qlora.py --data /kaggle/input/<ds>/sft --out /kaggle/working/p0 --limit 2000 --epochs 1
#   2. the script trains, then runs the GATE: fine-tuned vs untuned 1.5B on the validation split.
#   3. it writes go_no_go.json. Only if that says GO may you start 7B:
#        python train_qlora.py ... --base Qwen/Qwen2.5-Coder-7B-Instruct --go-file /kaggle/working/p0/go_no_go.json
#      The 7B run refuses to start without a GO from a 1.5B run.
#
# Secrets: only from Kaggle Secrets (Add-ons > Secrets), label HF_TOKEN, optional (Qwen is public).
# Nothing is read from arguments or files, and no secret is ever printed.
#
# Never train, tune or pick a threshold on the 86 frozen cases or `examples/`: this notebook only sees the mix.

# %%
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

IGNORE = -100
BASE_1_5B = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
SAVE_STEPS = 200                 # checkpoint cadence (spec); written under --out, i.e. /kaggle/working
VALID_VERDICTS = ("COMPLIANT", "DRIFT", "UNCERTAIN")


# %% [markdown]
# ## Secrets

# %%
def get_secret(name: str) -> str | None:
    """A Kaggle Secret, or None when not on Kaggle or not set. The value is never printed."""
    try:
        from kaggle_secrets import UserSecretsClient  # only exists inside Kaggle
        return UserSecretsClient().get_secret(name) or None
    except Exception:  # not on Kaggle, or secret missing
        return None


# %% [markdown]
# ## Data: tokenisation with loss on the completion only

# %%
def encode_example(tokenizer, record: dict, max_len: int) -> dict | None:
    """Tokenise one record. Returns None when it does not fit; truncating would cut the target."""
    *context, answer = record["messages"]
    if answer["role"] != "assistant":
        raise ValueError(f"{record.get('example_id')}: last message is not the assistant's")
    prompt_text = tokenizer.apply_chat_template(context, tokenize=False, add_generation_prompt=True)
    completion_text = answer["content"] + (tokenizer.eos_token or "")
    prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
    completion_ids = tokenizer(completion_text, add_special_tokens=False)["input_ids"]
    if len(prompt_ids) + len(completion_ids) > max_len:
        return None
    return {
        "input_ids": prompt_ids + completion_ids,
        "labels": [IGNORE] * len(prompt_ids) + completion_ids,       # loss on the completion only
    }


def load_records(path: Path, limit: int, seed: int) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit and len(rows) > limit:
        rows = random.Random(seed).sample(rows, limit)
    return rows


def encode_all(tokenizer, records: list[dict], max_len: int) -> tuple[list[dict], int]:
    encoded = [e for e in (encode_example(tokenizer, r, max_len) for r in records) if e]
    return encoded, len(records) - len(encoded)


def pad_batch(batch: list[dict], pad_id: int) -> dict:
    width = max(len(item["input_ids"]) for item in batch)
    ids, labels, mask = [], [], []
    for item in batch:
        gap = width - len(item["input_ids"])
        ids.append(item["input_ids"] + [pad_id] * gap)
        labels.append(item["labels"] + [IGNORE] * gap)
        mask.append([1] * len(item["input_ids"]) + [0] * gap)
    return {"input_ids": ids, "labels": labels, "attention_mask": mask}


# %% [markdown]
# ## The gate: does fine-tuning cut false alarms on validation?
#
# `answer_verdict` mirrors `specdrift/verify/verifier.py` (parse, then the evidence bar: a DRIFT without a
# quoted clause and a counterexample is UNCERTAIN; unparseable is UNCERTAIN). A test in the repo asserts the
# two stay equal, because this file is uploaded on its own and cannot import `specdrift`.

# %%
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _parse(text: str) -> dict | None:
    cleaned = _FENCE_RE.sub("", text or "").strip()
    if not cleaned:
        return None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = _OBJECT_RE.search(cleaned)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def answer_verdict(text: str) -> str:
    payload = _parse(text)
    if payload is None:
        return "UNCERTAIN"
    raw = str(payload.get("verdict", "")).strip().upper()
    verdict = raw if raw in VALID_VERDICTS else "UNCERTAIN"
    if verdict == "DRIFT":
        clause = str(payload.get("violated_clause") or "").strip()
        counter = payload.get("counterexample") or {}
        has_counter = bool(str(counter.get("input") or "").strip() and str(counter.get("actual") or "").strip())
        if not (clause and has_counter):
            return "UNCERTAIN"
    return verdict


def unparseable_rate(answers: list[str]) -> float:
    """Share of raw answers that contain no JSON object at all (they would all be read as UNCERTAIN)."""
    return round(sum(1 for a in answers if _parse(a) is None) / len(answers), 4) if answers else 0.0


def gate_metrics(labels: list[str], predictions: list[str]) -> dict:
    """False-alarm rate on COMPLIANT examples, recall on DRIFT examples, UNCERTAIN rate on both.

    UNCERTAIN-labelled examples are excluded: abstaining there is correct and neither a miss nor an alarm.
    """
    pairs = list(zip(labels, predictions, strict=True))
    negatives = [p for label, p in pairs if label == "COMPLIANT"]
    positives = [p for label, p in pairs if label == "DRIFT"]
    false_alarms = sum(1 for p in negatives if p == "DRIFT")
    caught = sum(1 for p in positives if p == "DRIFT")
    answered = negatives + positives
    return {
        "negatives": len(negatives),
        "false_alarms": false_alarms,
        "false_alarm_rate": round(false_alarms / len(negatives), 4) if negatives else 0.0,
        "positives": len(positives),
        "caught": caught,
        "recall": round(caught / len(positives), 4) if positives else 0.0,
        "uncertain_rate": round(sum(1 for p in answered if p == "UNCERTAIN") / len(answered), 4) if answered else 0.0,
    }


def decide_gate(base: dict, tuned: dict, min_negatives: int = 30, max_recall_drop: float = 0.05) -> dict:
    """GO only if the tuned model has a strictly lower false-alarm rate than the untuned one.

    Two guards keep that from being met cheaply. `min_negatives`: too few clean examples and a lower rate is
    noise. `max_recall_drop`: a model that never says DRIFT has no false alarms, so recall may not fall by more
    than this (absolute) against the untuned model; pass 1.0 to switch the guard off.
    """
    reasons: list[str] = []
    if base["negatives"] < min_negatives:
        reasons.append(f"only {base['negatives']} clean validation examples (need {min_negatives})")
    if not tuned["false_alarm_rate"] < base["false_alarm_rate"]:
        reasons.append(
            f"false-alarm rate did not fall: tuned {tuned['false_alarm_rate']:.3f} vs untuned {base['false_alarm_rate']:.3f}"
        )
        if base["false_alarm_rate"] == 0.0:
            reasons.append(
                "the untuned model raised no false alarm at all, so no improvement is possible; check `unparseable`: "
                "a model that cannot produce valid JSON never says DRIFT"
            )
    if tuned["recall"] < base["recall"] - max_recall_drop:
        reasons.append(
            f"recall fell by more than {max_recall_drop:.2f}: tuned {tuned['recall']:.3f} vs untuned {base['recall']:.3f}"
        )
    return {
        "decision": "NO_GO" if reasons else "GO",
        "reasons": reasons,
        "untuned": base,
        "tuned": tuned,
        "min_negatives": min_negatives,
        "max_recall_drop": max_recall_drop,
    }


def require_go(base_model: str, go_file: str | None) -> None:
    """A 7B run needs a GO written by a 1.5B run. Anything else exits before a GPU hour is spent."""
    if "7B" not in base_model.upper():
        return
    if not go_file or not Path(go_file).is_file():
        raise SystemExit(f"{base_model} needs --go-file pointing at the go_no_go.json written by a 1.5B run")
    gate = json.loads(Path(go_file).read_text(encoding="utf-8"))
    if gate.get("decision") != "GO" or "1.5B" not in str(gate.get("base", "")):
        raise SystemExit(
            f"gate says {gate.get('decision')} for {gate.get('base')}; fix the data before spending GPU quota on 7B"
        )


# %% [markdown]
# ## Training and gate run

# %%
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Folder with train.chat.jsonl, val.chat.jsonl, val.index.jsonl.")
    parser.add_argument("--out", required=True, help="Keep under /kaggle/working so checkpoints survive.")
    parser.add_argument("--base", default=BASE_1_5B)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-len", type=int, default=3072,
                        help="Examples longer than this are dropped, never truncated. Equals the data validator's "
                             "limit; use a smaller value for 7B (a test keeps the default in step with the validator).")
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--accum", type=int, default=8, help="batch x accum = effective batch 16")
    parser.add_argument("--limit", type=int, default=0, help="Sample this many training records (0 = all).")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--resume", action="store_true", help="Continue from the newest checkpoint in --out.")
    parser.add_argument("--skip-train", action="store_true", help="Only run the gate on --adapter (or --out/adapter).")
    parser.add_argument("--adapter", default="")
    parser.add_argument("--go-file", default="", help="go_no_go.json from a 1.5B run; required for 7B.")
    parser.add_argument("--gate-data", default="",
                        help="Folder with val.chat.jsonl and val.index.jsonl to gate on (default: --data). Gate every "
                             "ablation arm on the same validation set, or their gate numbers are not comparable.")
    parser.add_argument("--gate-batch", type=int, default=8)
    parser.add_argument("--gate-limit", type=int, default=0, help="Use only this many validation records (0 = all).")
    parser.add_argument("--min-negatives", type=int, default=30)
    parser.add_argument("--max-recall-drop", type=float, default=0.05)
    return parser


def warmup_steps(total_steps: int, ratio: float = 0.03) -> int:
    """Warm-up as an integer step count. `TrainingArguments(warmup_ratio=...)` was removed in newer transformers,
    while `warmup_steps=<int>` works in every version."""
    return max(1, round(total_steps * ratio))


def load_model(base: str, token: str | None):
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16,
                               bnb_4bit_use_double_quant=True)
    # fp16 everywhere: the T4 has no bf16.
    return AutoModelForCausalLM.from_pretrained(base, quantization_config=quant, torch_dtype=torch.float16,
                                                device_map="auto", token=token)


def train(args, tokenizer, token: str | None):
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import Trainer, TrainingArguments

    data = Path(args.data)
    train_rows, dropped_train = encode_all(
        tokenizer, load_records(data / "train.chat.jsonl", args.limit, args.seed), args.max_len)
    val_rows, dropped_val = encode_all(tokenizer, load_records(data / "val.chat.jsonl", 0, args.seed), args.max_len)
    print(f"train {len(train_rows)} (dropped {dropped_train} over {args.max_len} tokens), "
          f"val {len(val_rows)} (dropped {dropped_val})")
    if not train_rows or not val_rows:
        raise SystemExit("nothing to train or validate on")

    model = prepare_model_for_kbit_training(load_model(args.base, token))
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules="all-linear"))
    model.print_trainable_parameters()

    class Rows(torch.utils.data.Dataset):
        def __init__(self, rows):
            self.rows = rows

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            return self.rows[index]

    def collate(batch):
        return {k: torch.tensor(v) for k, v in pad_batch(batch, tokenizer.pad_token_id).items()}

    steps_per_epoch = max(1, -(-len(train_rows) // (args.batch * args.accum)))
    total_steps = max(1, math.ceil(steps_per_epoch * args.epochs))
    arguments = TrainingArguments(
        output_dir=args.out, num_train_epochs=args.epochs, learning_rate=args.lr, lr_scheduler_type="cosine",
        warmup_steps=warmup_steps(total_steps), per_device_train_batch_size=args.batch, per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.accum, fp16=True, gradient_checkpointing=True,
        eval_strategy="steps", eval_steps=min(SAVE_STEPS, steps_per_epoch),   # small sets are still evaluated each epoch
        save_strategy="steps", save_steps=SAVE_STEPS, save_total_limit=2,
        logging_steps=20, seed=args.seed, report_to="none", remove_unused_columns=False,
    )
    trainer = Trainer(model=model, args=arguments, train_dataset=Rows(train_rows), eval_dataset=Rows(val_rows),
                      data_collator=collate)
    has_checkpoint = any(Path(args.out).glob("checkpoint-*"))
    trainer.train(resume_from_checkpoint=bool(args.resume and has_checkpoint))
    adapter = Path(args.out) / "adapter"
    model.save_pretrained(adapter)
    tokenizer.save_pretrained(adapter)
    (Path(args.out) / "run.json").write_text(json.dumps(
        {"base": args.base, "train": len(train_rows), "val": len(val_rows), "dropped_train": dropped_train,
         "epochs": args.epochs, "lr": args.lr, "seed": args.seed, "log": trainer.state.log_history}, indent=1))
    print("adapter saved to", adapter)
    return model


def generate_answers(model, tokenizer, records: list[dict], batch: int) -> list[str]:
    """Greedy answers for the prompt part of each chat record (left-padded batches)."""
    tokenizer.padding_side = "left"
    texts = [tokenizer.apply_chat_template(r["messages"][:-1], tokenize=False, add_generation_prompt=True)
             for r in records]
    answers: list[str] = []
    for start in range(0, len(texts), batch):
        enc = tokenizer(texts[start:start + batch], return_tensors="pt", padding=True,
                        add_special_tokens=False).to(model.device)
        out = model.generate(**enc, max_new_tokens=300, do_sample=False, pad_token_id=tokenizer.pad_token_id)
        answers += tokenizer.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
    return answers


def gate_dir(args) -> Path:
    """The validation set the gate runs on: --gate-data if given, else the training folder's own."""
    return Path(args.gate_data or args.data)


def run_gate(model, tokenizer, args) -> dict:
    """Same weights, adapter off vs on, over the validation split: no reload, no other difference."""
    data = gate_dir(args)
    records = load_records(data / "val.chat.jsonl", args.gate_limit, args.seed)
    labels_by_id = {row["example_id"]: row["label"]
                    for row in map(json.loads, (data / "val.index.jsonl").read_text(encoding="utf-8").splitlines())}
    labels = [labels_by_id[r["example_id"]] for r in records]
    model.eval()
    with model.disable_adapter():
        untuned_raw = generate_answers(model, tokenizer, records, args.gate_batch)
    tuned_raw = generate_answers(model, tokenizer, records, args.gate_batch)
    gate = decide_gate(gate_metrics(labels, [answer_verdict(a) for a in untuned_raw]),
                       gate_metrics(labels, [answer_verdict(a) for a in tuned_raw]),
                       args.min_negatives, args.max_recall_drop)
    gate["base"] = args.base
    gate["validation_examples"] = len(records)
    gate["validation_data"] = str(data)
    gate["unparseable_rate"] = {"untuned": unparseable_rate(untuned_raw), "tuned": unparseable_rate(tuned_raw)}
    (Path(args.out) / "go_no_go.json").write_text(json.dumps(gate, indent=1), encoding="utf-8")
    return gate


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    require_go(args.base, args.go_file)
    Path(args.out).mkdir(parents=True, exist_ok=True)

    from transformers import AutoTokenizer

    token = get_secret("HF_TOKEN")
    tokenizer = AutoTokenizer.from_pretrained(args.base, token=token)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    if args.skip_train:
        from peft import PeftModel
        model = PeftModel.from_pretrained(load_model(args.base, token), args.adapter or str(Path(args.out) / "adapter"))
    else:
        model = train(args, tokenizer, token)

    gate = run_gate(model, tokenizer, args)
    print(json.dumps({k: gate[k] for k in ("decision", "reasons", "untuned", "tuned")}, indent=1))
    print(f"\nGATE: {gate['decision']}.", "Safe to try 7B." if gate["decision"] == "GO"
          else "Do NOT start 7B; fix the data first (label noise, balance).")
    sys.exit(0 if gate["decision"] == "GO" else 2)


# %%
if __name__ == "__main__":
    main()
