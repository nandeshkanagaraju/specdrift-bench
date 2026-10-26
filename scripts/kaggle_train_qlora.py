"""QLoRA fine-tune of a small Qwen2.5-Coder on the SFT export (docs/training-data-spec.md, section 9).

Self-contained on purpose: upload this one file plus the `sft/` folder from `specdrift data-sft`
as a private Kaggle dataset. Loss is computed on the completion tokens only, and the prompt is
rendered with the model's own chat template plus the generation prompt, so training sees exactly
what `HuggingFaceLLM` feeds the model at inference time.

    python kaggle_train_qlora.py --data /kaggle/input/specdrift-sft --out /kaggle/working/m1 \
        --base Qwen/Qwen2.5-Coder-1.5B-Instruct

Smoke test (P0): add `--limit 2000 --epochs 1`. T4 has no bf16, so fp16 is used.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

IGNORE = -100


def encode_example(tokenizer, record: dict, max_len: int) -> dict | None:
    """Tokenise one record. Returns None when it does not fit; truncating would cut the target."""
    prompt_text = tokenizer.apply_chat_template(record["prompt"], tokenize=False, add_generation_prompt=True)
    completion_text = record["completion"][0]["content"] + (tokenizer.eos_token or "")
    prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
    completion_ids = tokenizer(completion_text, add_special_tokens=False)["input_ids"]
    if len(prompt_ids) + len(completion_ids) > max_len:
        return None
    return {
        "input_ids": prompt_ids + completion_ids,
        "labels": [IGNORE] * len(prompt_ids) + completion_ids,
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Folder holding train.jsonl and val.jsonl (from data-sft).")
    parser.add_argument("--out", required=True)
    parser.add_argument("--base", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-len", type=int, default=1536)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--accum", type=int, default=8, help="batch x accum = effective batch (16)")
    parser.add_argument("--limit", type=int, default=0, help="Sample this many training records (0 = all).")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--save-steps", type=int, default=200)
    args = parser.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainingArguments,
    )

    data = Path(args.data)
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    train, dropped_train = encode_all(tokenizer, load_records(data / "train.jsonl", args.limit, args.seed), args.max_len)
    val, dropped_val = encode_all(tokenizer, load_records(data / "val.jsonl", 0, args.seed), args.max_len)
    print(f"train {len(train)} (dropped {dropped_train} over {args.max_len} tokens), "
          f"val {len(val)} (dropped {dropped_val})")
    if not train or not val:
        raise SystemExit("nothing to train or validate on")

    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16,
                               bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(args.base, quantization_config=quant, torch_dtype=torch.float16,
                                                 device_map="auto")
    model = prepare_model_for_kbit_training(model)
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

    steps_per_epoch = max(1, -(-len(train) // (args.batch * args.accum)))
    interval = min(args.save_steps, steps_per_epoch)      # a small set must still be evaluated every epoch
    arguments = TrainingArguments(
        output_dir=args.out, num_train_epochs=args.epochs, learning_rate=args.lr, lr_scheduler_type="cosine",
        warmup_ratio=0.03, per_device_train_batch_size=args.batch, per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.accum, fp16=True, gradient_checkpointing=True,
        eval_strategy="steps", eval_steps=interval, save_strategy="steps", save_steps=interval,
        save_total_limit=2, logging_steps=20, seed=args.seed, report_to="none", remove_unused_columns=False,
        load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False,
    )
    trainer = Trainer(model=model, args=arguments, train_dataset=Rows(train), eval_dataset=Rows(val),
                      data_collator=collate)
    trainer.train()
    model.save_pretrained(args.out + "/adapter")
    tokenizer.save_pretrained(args.out + "/adapter")
    (Path(args.out) / "run.json").write_text(json.dumps(
        {"base": args.base, "train": len(train), "val": len(val), "dropped_train": dropped_train,
         "epochs": args.epochs, "lr": args.lr, "seed": args.seed, "log": trainer.state.log_history}, indent=1))
    print("adapter saved to", args.out + "/adapter")


if __name__ == "__main__":
    main()
