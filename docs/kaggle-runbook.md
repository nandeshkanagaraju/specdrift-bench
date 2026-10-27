# Runbook: from a mix to a measured comparison

Tested on the Mac: the export, the verdict parser shared with the gate, the gate logic, the Hugging Face provider (against fakes), the
held-out runner (with the offline stand-in) and the whole comparison report. **Not run anywhere yet:** the Kaggle notebook's GPU paths
(model loading, training, generation) and the Hugging Face provider against a real model. Expect to fix a first-run problem or two.

Do the human spot-check (`docs/pilot-spot-check.md`) before treating any number from this path as a result.

## 1. Export (Mac)

```
.venv/bin/specdrift data-sft data/mix/<name>
# writes data/mix/<name>/sft/{train,val}.chat.jsonl (messages), {train,val}.jsonl (system/prompt/completion text),
# {train,val}.index.jsonl (label, category, project: metadata, never shown to the model) and sft.json (stats)
```

Loss must be computed on the completion (assistant message) only. Token counts in `sft.json` are an estimate (no tokenizer offline).

## 2. Train and gate (Kaggle, GPU T4 x2 or P100)

Upload `data/mix/<name>/sft/` and `scripts/kaggle/train_qlora.py` as one private dataset. In a notebook:

```
!pip install -q peft bitsandbytes "transformers>=4.45" accelerate
!python train_qlora.py --data /kaggle/input/<dataset>/sft --out /kaggle/working/p0 --limit 2000 --epochs 1
```

The script trains Qwen2.5-Coder-1.5B-Instruct (QLoRA, fp16, r=16, alpha=32, dropout 0.05, all linear layers, LR 2e-4 cosine, effective
batch 16, checkpoint every 200 steps under `--out`), then runs the **gate** on the validation split with the same weights, adapter off
versus on, and writes `go_no_go.json`:

- GO only if the fine-tuned model's false-alarm rate on clean validation examples is strictly lower than the untuned model's,
  with at least 30 clean examples, and its recall has not fallen by more than 0.05 (a model that never says DRIFT has no false alarms).
  The recall condition and both thresholds are my addition to the spec's "beat the untuned 1.5B on validation false-alarm rate";
  change `--max-recall-drop` / `--min-negatives` if you disagree (1.0 switches the recall guard off).
- Exit code 0 on GO, 2 on NO_GO. A session that dies can continue with `--resume`, or re-run just the gate with `--skip-train --adapter <dir>`.
- The 7B run (`--base Qwen/Qwen2.5-Coder-7B-Instruct --go-file <p0>/go_no_go.json`) refuses to start without a GO written by a 1.5B run.
- The only secret is an optional `HF_TOKEN` in Kaggle Secrets; nothing is read from arguments or files.

Download `<out>/adapter` (tens of MB), `run.json` (loss log) and `go_no_go.json`.

## 3. Compare (Mac with a GPU, or Kaggle)

Copy `scripts/compare_arms.example.json`, fill the `<<placeholders>>` (stronger zero-shot model id, adapter path). Install
`torch transformers peft bitsandbytes` where the Hugging Face arms run.

```
python scripts/compare_models.py run    --arms my_arms.json --out results_compare             # prints the plan, runs nothing
python scripts/compare_models.py run    --arms my_arms.json --out results_compare --execute   # 3 runs per arm
python scripts/compare_models.py report --arms my_arms.json --out results_compare             # comparison.md and comparison.json
```

Each arm runs `specdrift run --repeat 3` on the 86 cases and, for specguard arms, `specdrift heldout --repeat 3` on the `examples/`
projects, with `RESULTS_DIR=<out>/<arm>`. An arm may set `results_dir` to reuse existing results instead of re-running (use it for the
current gpt-4o-mini results). Arms can only override `LLM_PROVIDER, LLM_MODEL, LLM_ADAPTER, LLM_BASE_URL, LLM_MAX_TOKENS, EMBED_*, TOP_K`;
API keys stay in `.env`. Arms answered by the offline stand-in are labelled FAKE in the report.

The report has, per arm: recall, precision, strict precision, false-alarm rate, UNCERTAIN rate and ECE with bootstrap 95% CIs; per-category
recall / false-alarm rate; the abstention coverage-against-accuracy curve; a paired difference against the baseline arm (what H1 asks);
and the test-2 table. Its last section lists the caveats to quote with any number.

## 4. The first real run: mixes, launch order, stop rules (26 Oct 2026)

**Update, 26 Oct (later):** `data/mix/main-v2` supersedes `main-v1` as the main mix. It adds iniconfig and tomli, was built after the token limit
went to 2,048 and after two classifier fixes (test ids with spaces, pytest-9 `SUBFAILED` subtest lines), and has **828 train / 162 val** examples
(289 / 456 / 83 DRIFT / COMPLIANT / UNCERTAIN; synthetic part from semver, voluptuous, iniconfig and tomli; largest project 21%).
`data/mix/main-v3` adds colorama and supersedes `main-v2`: **1,028 train / 162 val** (360 / 565 / 103 DRIFT / COMPLIANT / UNCERTAIN; five synthetic
libraries; largest project 16%). `data/mix/main-v4` adds flashtext and xmltodict and supersedes it: **1,404 train / 162 val**
(492 / 772 / 140; seven synthetic libraries; no project above 15%), but flashtext's and xmltodict's longest functions are mostly missing because their
examples exceeded the then-current 2,048-token limit (196 rejected). **The validator limit is now 3,072** (`MAX_TOKENS`; the notebook's `--max-len` default
matches, and the 7B M2 run uses `--max-len 1536`), so iniconfig, tomli, flashtext and xmltodict must be re-run to recover those examples (colorama had no
rejections), and schema and tabulate are new. **Those runs are done and `data/mix/main-v5` supersedes `main-v4`: 1,788 train / 162 val** (625 / 984 / 179
DRIFT / COMPLIANT / UNCERTAIN; nine synthetic libraries plus Stage A; no project above 18% of a label; no example over 3,072 tokens; leakage check clean;
SFT export in `main-v5/sft`; validation is still the single project `cachetools`). tabulate is the weak contributor (10 of 20 rules with a DRIFT
example, 42 examples) because `tabulate()` itself is about 750 lines and is rejected for length.
**`data/mix/main-v6` adds pyflakes (the last repo) and supersedes `main-v5`: 1,921 train / 162 val**, same label shares, ten synthetic libraries, no project
above 19% of a label, leakage check clean, no example over 3,072 tokens, SFT export in `main-v6/sft`. pyflakes has 18 of 20 rules with a DRIFT example
(R03 `isPythonFile` and R04 `iterSourceCode` have none: the R03 oracle cannot tell `"~"` from `"~x"` for a nonexistent file). R0 should use `main-v6`.
semver, cachetools and voluptuous were generated under the old limit and classifier and have not been re-run.

**The ablation mixes and size-matched controls were rebuilt on the `main-v6` pool** (same `data-mix` flags as the `main-v1` versions, 26 Oct 2026).
Validation project is `cachetools`. Every mix is exported with `data-sft` under `data/mix/<name>/sft/`; none has an example over 3,072 tokens.
The older `main-v1-*` mixes are superseded and should not be trained on.

| mix | train / val | pairs with | question |
|---|---|---|---|
| `main-v6` | 1,921 / 162 | | the main model |
| `main-v6-nopaper` | 1,281 / 108 | `main-v6-n1281` (random subsample of main-v6, 384 paper) | H3: does Stage A help? (same n) |
| `main-v6-noN23` | 912 / 81 | `main-v6-n912` | H2: do N2/N3 hard negatives cut false alarms? (same n) |
| `main-v6-heldout` | 1,514 / 127 | `main-v6-n1514` | does it hold up when the benchmark-overlapping families (`rename_local`, `extract_temp`, `decoy_comment`, `decoy_docstring`) are held out of training? |

Checked on the built files: `nopaper` has no Stage A examples, `noN23` has none of its nine excluded operators, `heldout` has none of its four, and each
control has the size of its partner. The ablations shrink the data a lot (N2/N3 are most of the synthetic COMPLIANT examples), so compare each only with its
size-matched control, never with `main-v6`. **Gate every arm on the same validation set**: `--gate-data data/mix/main-v6/sft`. Gate numbers from different
validation sets are not comparable. The three controls share the 162-example validation set; the ablation mixes have smaller ones (108, 81, 127), so the
gate must always point at `main-v6/sft`, not at the arm's own `sft/`.

**Launch order**

1. **R0, the pilot**: `main-v6`, seed 17, 2 epochs, `--gate-data data/mix/main-v6/sft`. About 1,921 / batch-size optimiser steps per epoch (the old
   52-step figure was for the 414-example `main-v1`; recompute from your batch size and check whether the 200-step checkpoint is now reached).
   Read `go_no_go.json`.
   **R0 result (26 Oct 2026, Kaggle 2x T4, `main-v6`, seed 17, 2 epochs, 240 steps, 1h46m): GO.** 1,913 of 1,921 examples trained (8 were over 3,072 tokens by the real
   tokenizer). On the 162 validation examples (cachetools only; 89 clean, 57 DRIFT): false-alarm rate 0.494 untuned (44/89) vs 0.157 tuned (14/89); recall
   0.404 for both (23/57 caught); UNCERTAIN rate 0.541 vs 0.130; unparseable rate 0.191 vs 0.000. S1 to S3 do not fire. The smoke test found one real bug
   (newer transformers rejects `warmup_ratio`; fixed with `warmup_steps`). Not yet measured on the 86 cases (R1), so S4 is still open. Recall did not improve,
   and part of the false-alarm drop may be the tuned model learning the output format (the untuned model's answers are unparseable 19% of the time).
   **The R0 adapter itself was lost** (the Kaggle session's working folder was overwritten before it was downloaded or saved as a version), so R0 is being
   retrained inside one combined R0 + R1 notebook that saves `r0_adapter.zip`. GPU training is not guaranteed bit-identical, so the retrained gate numbers
   may differ a little from the ones above; the numbers above are from the lost adapter. Always use Save Version and download the adapter straight away.
   **R0 retrained (27 Oct 2026, same data, script and seed 17): NO_GO.** Training and validation loss were almost identical to the first run (first-epoch eval loss
   0.0910 then 0.0914), but the gate differed: false alarms 11/89 (0.124) vs 14/89 (0.157) before, tuned unparseable 0.006, recall **15/57 (0.263)** vs 23/57
   (0.404) before, so S1 fired on the recall guard (untuned 0.404; drop 0.14 > 0.05). Reading: the false-alarm reduction repeated (0.494 down to 0.12 to 0.16);
   recall did not, and it was never above the untuned model's in either run. On 57 drift examples a recall of 0.263 and one of 0.404 have overlapping 95% Wilson
   intervals (about 0.17 to 0.39 and 0.29 to 0.53), so the 0.05 recall guard is below what this validation set (one project) can resolve. The guard was
   fixed before the runs and is left as it is; the fix is a larger, multi-project validation set. Cause found in the script: `--seed` did not seed the LoRA
   initial weights (they are created before the Trainer applies the seed); fixed with `set_seed` before the model is built, so the retrain above ran
   WITHOUT that fix and the first run's result cannot be reproduced.
   **R0 run 3 (27 to 28 Oct 2026; trained inside the R1 notebook session): NO_GO.** False alarms 8/89 (0.090), recall 18/57 (0.316), tuned unparseable 0.006, so
   S1 fired on the recall guard again. Three runs now: GO (14/89, 23/57; adapter lost), NO_GO (11/89, 15/57; run 2, never run on the benchmark), NO_GO (8/89,
   18/57; run 3). The notebook's stop-rule cell halted after the gate and the R1 cells were then run by hand as a diagnostic.
   **R1 (28 Oct 2026, scored the run-3 adapter, diagnostic past an S1 NO_GO; untuned and tuned run in parallel on 2x T4, about 1h45m):** on the 86 cases the tuned
   model has false-alarm rate 0.00 and recall **0.08** [0.02, 0.16] (gpt-4o-mini: 0.65 and 0.54; untuned Qwen: 0.96 and 0.42); on `examples/` its recall is 0.00.
   It says COMPLIANT almost everywhere, so H1 (lower false alarms at equal or better recall) is not supported. S4 is met literally but through that
   collapse. The validation recall (0.32 for this adapter, 0.26 to 0.40 across runs) did not predict the benchmark recall (0.08). Full tables: `docs/r1-comparison.md` and
   `docs/trained-model-evaluation.md`. Not done and not run: ablations (R2), seeds (R1b), 7B.
   **Scoring experiment (28 Oct 2026, run-3 adapter, about 8 minutes of GPU time):** ranking rule checks by the probability of the first answer token gives benchmark
   AUC 0.51 [0.44, 0.59] (untuned 0.45), so there is no ranking signal hidden by the answers and recalibrating cannot fix it. Validation AUC is 0.73 overall but 0.60 on the
   synthetic project-level part; at the validation-chosen threshold recall is 12 of 19 on function-level paper examples and 8 of 38 on synthetic ones (exploratory).
   The failure is in what was learned, so the next change should be to the training signal (more or better project-level drift examples, a validation set that
   separates function-level from project-level), not to thresholds.
2. **R1, evaluate R0 on the 86 cases**: untuned Qwen and R0, one run each (`"runs": 1` in the arms file; greedy decoding is deterministic, repeating it
   only burns GPU). Time `specdrift run --detector specguard --limit 5` first: each case is about 13 separate generations, and the full 86 cases may take
   hours per arm (an estimate, not measured). The gpt-4o-mini arm reuses `results/`.
3. **R1b, seed noise**: `main-v6` again with seeds 18 and 19 (train and gate only). This gives the spread any ablation difference has to beat.
4. **R2, ablations**, one seed each, in this order: `n912` then `noN23` (H2), `n1281` then `nopaper` (H3), `n1514` then `heldout` (all `main-v6-` prefixed), every one
   gated on `data/mix/main-v6/sft`. Evaluate on the 86 cases only for pairs whose gate result is not NO_GO.
5. Only after a GO and a clean R1: the 7B pilot, and scaling the data.

**Stop, and do not launch the next step, if:**

- **S1**: R0's gate says NO_GO. Read the reasons first; one of them is a floor effect (the untuned model raised no false alarm, usually because it cannot produce valid JSON).
- **S2**: R0's tuned `unparseable_rate` is above 0.05. The output format was not learned (too few steps or a data problem), and every other number is then meaningless.
- **S3**: R0's tuned validation recall is below 0.15 (collapse to "COMPLIANT"). A lower false-alarm rate bought that way is not an improvement.
- **S4**: after R1, the tuned arm's false-alarm rate on the 86 cases is not below the untuned Qwen's. Ablating a model that shows no effect measures noise.
- **S5**: after R1b, the false-alarm rate on validation differs by more than 0.10 between seeds. 89 clean examples resolve about that much, so smaller ablation gaps cannot be read.
- **S6**: any `data-mix`, `data-sft` or `data-check` run reports a leakage violation. Nothing goes to Kaggle until it is clean.

These thresholds are my proposals, not results; change them before launching, not after seeing the numbers.

## 5. Still open

- `examples/expected.json` has ground truth for 3 of the 4 test-2 projects; `clinic-desk` has none, and none of it has oracle tests behind it.
- Data scaling is done (`main-v6`, 1,921 training examples from ten libraries plus Stage A). Validation is still the single project `cachetools`.
- A stronger zero-shot comparison model needs an API key and a choice of model.
