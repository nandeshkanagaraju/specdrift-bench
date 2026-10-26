# Runbook: from a mix to a measured comparison

Everything on the Mac is tested; the Kaggle step has only had its tokenisation and masking logic tested (no GPU here).
Do the human spot-check (`docs/pilot-spot-check.md`) before treating any number from this path as a result.

## 1. Export (Mac)

```
.venv/bin/specdrift data-sft data/mix/<name>          # writes data/mix/<name>/sft/{train,val}.jsonl, sft.json
```

Re-runs the frozen-test-set check, then refuses (exit 1) any example whose own completion, read by the production
parser, would not give its label (for example a DRIFT without a counterexample, which the verifier would downgrade).
Prompt = `SYSTEM_PROMPT` + `build_user_prompt` at `PROMPT_VERSION` v1; change the prompt and you must re-export.

## 2. Train (Kaggle, GPU T4 x2 or P100)

Upload `data/mix/<name>/sft/` and `scripts/kaggle_train_qlora.py` as one private dataset. In a notebook:

```
!pip install -q peft bitsandbytes "transformers>=4.45" accelerate
!python kaggle_train_qlora.py --data /kaggle/input/<dataset>/sft --out /kaggle/working/p0 --limit 2000 --epochs 1
```

P0 is the go/no-go (section 11 of the training spec). Then run M1 without `--limit`, `--epochs 2`.
Download `/kaggle/working/<run>/adapter` (tens of MB) and `run.json` (loss log). Training drops, never truncates, examples over
`--max-len` tokens and prints how many.

## 3. Evaluate the same 86 cases (Mac with a GPU, or Kaggle)

Install `torch transformers peft bitsandbytes` where you evaluate. One results directory per model, so runs never overwrite each other;
the model name (including the adapter) is part of the response-cache key.

```
# baseline already in results/ (gpt-4o-mini)
RESULTS_DIR=results_qwen_base LLM_PROVIDER=huggingface LLM_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct \
  specdrift run --detector specguard --repeat 3
RESULTS_DIR=results_qwen_m1   LLM_PROVIDER=huggingface LLM_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct LLM_ADAPTER=/path/to/adapter \
  specdrift run --detector specguard --repeat 3
RESULTS_DIR=results_qwen_m1 specdrift score --detector specguard
RESULTS_DIR=results_qwen_m1 specdrift stability --detector specguard
```

Compare per model: recall, strict precision, false-alarm rate, UNCERTAIN rate, with the bootstrap CIs from `stability`.
H1 holds only if the false-alarm interval for M1 lies below gpt-4o-mini's at equal or better recall. Report the table either way.

## 4. Still open

- The `examples/` projects (test-2) need oracles before they can score the model.
- A stronger zero-shot comparison model needs an API key; the base-Qwen row is the untuned open model.
- Scale the data first (8 more verified repos, generator that is not gpt-4o-mini); the pilot mix has 414 training examples and is a rehearsal.
