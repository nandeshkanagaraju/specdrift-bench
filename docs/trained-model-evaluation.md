# Evaluating a fine-tuned Stage 2 verifier (27 Oct 2026)

Answers the panel's remark "Evaluate the model properly" with a measured comparison. **The headline is a negative result for H1**: the fine-tuned
model removes the false alarms but also stops detecting drift (section 4). A negative or mixed result is reported as such (training-data-spec.md, section on H1).

## 1. Question

**H1**: a fine-tuned small open model, used as SpecGuard's Stage 2 verifier, has a lower false-alarm rate than zero-shot `gpt-4o-mini` at equal or better
recall, measured on the 86 frozen cases (DRIFT is the positive class). The baseline is the untuned base model and `gpt-4o-mini`.

## 2. What was built and trained

- **Model:** Qwen2.5-Coder-1.5B-Instruct, QLoRA (4-bit NF4, fp16, LoRA r=16, alpha 32, dropout 0.05, all linear layers), 2 epochs, learning rate 2e-4 cosine,
  effective batch 16, 240 optimiser steps, seed 17, about 1h49m on 2x T4. Loss is computed on the answer only.
- **Training data (`main-v6`):** 1,921 examples: 625 DRIFT, 984 COMPLIANT, 179 UNCERTAIN. Sources: ten open-source Python libraries (iniconfig, tomli,
  colorama, flashtext, xmltodict, schema, tabulate, pyflakes, semver, voluptuous; rules and oracles written interactively by Claude, not through an
  API), mutation-based DRIFT examples whose labels come from executable oracles (an oracle must pass on the original and fail on the mutant),
  behaviour-preserving refactors and decoys as hard negatives, abstention examples, and a function-level paper dataset (Stage A, about 30%).
  Validation is the single project `cachetools` (162 examples: 57 DRIFT, 89 clean, 16 UNCERTAIN). 8 of 1,921 examples were dropped for exceeding 3,072
  tokens.
- **Leakage controls:** the 86 cases and the `examples/` projects are never used for training or tuning (`data-check`, `data-mix` and `data-sft`
  compare against a frozen manifest; every mix was clean).

## 3. Gate result on the validation set (R0)

The go/no-go gate: the tuned model's false-alarm rate on clean validation examples must be strictly lower than the untuned model's (at least 30 clean
examples), and its recall must not fall by more than 0.05.

Three training runs with the same data, script and seed 17 (the seed did not control the adapter's starting weights, see below):

| 162 validation examples | untuned | run 1 (adapter lost) | run 2 (not evaluated on the benchmark) | run 3 (**the adapter R1 evaluated**) |
|---|---|---|---|---|
| false alarms among 89 clean | 44 (0.494) | 14 (0.157) | 11 (0.124) | 8 (0.090) |
| DRIFT caught among 57 | 23 (0.404) | 23 (0.404) | 15 (0.263) | 18 (0.316) |
| UNCERTAIN rate | 0.541 | 0.130 | 0.144 | 0.123 |
| unparseable answers | 0.191 | 0.000 | 0.006 | 0.006 |
| gate | | GO | NO_GO (recall guard) | NO_GO (recall guard) |

Reading: the false-alarm reduction and the parseable output repeated in all three runs (0.09 to 0.16 against 0.49 untuned); recall did not improve in any, and the
caught count was 23, 15 and 18 across runs with the same settings and near-identical losses (first-epoch validation loss 0.0910, 0.0914 and the same
pattern in run 3). With 57 DRIFT examples the 95% Wilson intervals for 0.263 and 0.404 (about 0.17 to 0.39 and 0.29 to 0.53) overlap, so the 0.05 recall guard
is below what this one-project validation set can resolve. The guard was fixed before the runs and is reported as it fired (two of three runs failed it). A script
defect explains part of the run-to-run difference: `--seed` did not seed the LoRA initial weights (fixed afterwards; none of the three runs used the fix).

Which adapter is which: run 3 was trained inside the R1 notebook session (gate recall 0.316, false alarms 8 of 89) and R1 scored it; run 2 came from a separate
session and its adapter was never run on the benchmark. An earlier version of this document attributed the R1 numbers to run 2; that was wrong.

## 4. Benchmark comparison (R1)

Arms: `gpt-4o-mini` zero-shot (existing results, 3 runs), untuned Qwen2.5-Coder-1.5B (1 run, greedy decoding is deterministic), the **run-3** R0 adapter
(1 run; validation gate NO_GO with recall 0.316 and false alarms 8 of 89). Run on 86 cases plus the unseen `examples/` projects by `scripts/compare_models.py`; bootstrap 95% CIs over cases.

Mean over runs, bootstrap 95% CI over cases. DRIFT is the positive class. The full report is `docs/r1-comparison.md`.

| arm (runs) | recall | precision | strict precision | false-alarm rate | UNCERTAIN rate |
|---|---|---|---|---|---|
| gpt-4o-mini zero-shot (3) | 0.54 [0.41, 0.66] | 0.64 [0.51, 0.77] | 0.29 [0.22, 0.36] | 0.65 [0.47, 0.83] | 0.06 |
| keyword baseline (1) | 0.08 [0.02, 0.16] | 0.33 [0.10, 0.60] | 0.16 [0.04, 0.29] | 0.37 [0.19, 0.56] | 0.00 |
| Qwen2.5-Coder-1.5B untuned (1) | 0.42 [0.31, 0.56] | 0.49 [0.35, 0.63] | 0.09 [0.06, 0.11] | 0.96 [0.88, 1.00] | 0.65 |
| Qwen2.5-Coder-1.5B + R0 adapter (1) | **0.08 [0.02, 0.16]** | 1.00 [1.00, 1.00] | 0.50 [0.22, 0.78] | **0.00 [0.00, 0.00]** | 0.05 |

Paired differences, tuned arm minus baseline, same 86 cases:

| against | false-alarm rate | recall |
|---|---|---|
| gpt-4o-mini zero-shot | -0.65 [-0.83, -0.47] (lower) | -0.46 [-0.59, -0.31] (lower) |
| untuned Qwen | -0.96 [-1.00, -0.88] (lower) | -0.34 [-0.47, -0.22] (lower) |

Unseen `examples/` projects (test-2; 34 rules, 10 drifted; gpt-4o-mini has no results here): untuned recall 0.30 [0.00, 0.60], false-alarm rate 0.38;
tuned recall **0.00** [0.00, 0.00], false-alarm rate 0.08 [0.00, 0.21].

**Reading.** The tuned model almost never answers DRIFT on the hand-built benchmark: of the nine drift categories its recall is 0.00 in six, and its
precision of 1.00 and false-alarm rate of 0.00 come from saying COMPLIANT nearly everywhere (95% coverage, 95% accuracy per case-rule pair, because most
pairs are compliant). That is the failure the gate's recall guard exists to catch, and the benchmark shows it much more strongly than the validation set did
(recall 0.08 here against 0.32 for the same adapter on validation, and 0.26 to 0.40 across the three runs). H1 asks for a lower false-alarm rate **at equal or better recall**: the false-alarm rate is lower than
both baselines, the recall is lower than both too (the interval against gpt-4o-mini excludes zero), so **H1 is not supported**. Stop rule S4 (tuned
false-alarm rate below the untuned model's) is met literally (0.00 against 0.96), but only through that collapse, so it is not evidence of a better verifier.
The untuned 1.5B model is itself a poor verifier here (false-alarm rate 0.96, UNCERTAIN rate 0.65), which makes it an easy baseline to beat on false
alarms and a weak one to compare against.

**A hypothesis, not a finding:** validation used the same kinds of synthetic mutation as training (a different library, the same operators), while the
benchmark's drifts were written by hand. The gap between recall 0.32 (this adapter) on validation and 0.08 on the benchmark is consistent with the model learning
the injected-mutation patterns rather than drift in general. The `main-v6-heldout` mix (benchmark-overlapping operator families held out) was built to test
exactly this and has not been trained.

## 5. Threats to validity (state these next to any number)

- **One trained model, one seed.** Run-to-run variation is not measured; section 3 shows it is large relative to the recall guard. The CI in section 4
  covers case sampling only, not training variation.
- **Single validation project** (`cachetools`), so the gate and any model selection rest on 162 examples from one library.
- **Gate verdict:** the evaluated adapter (run 3) failed the pre-set gate (NO_GO), as did run 2; only the lost run 1 passed. Section 4 is a diagnostic evaluation past that stop rule, not a result that
  licenses ablations or the 7B model.
- **Contamination:** the Stage A function-level data and the base model may have seen related code; the benchmark's cases are hand-built, which limits but
  does not remove this.
- **Labels and rules were written by an LLM** (Claude, acting as generator) and checked by executable oracles and lint gates, not by humans; the human
  spot-check (`docs/pilot-spot-check.md`) is outstanding.
- **Test-2 coverage:** `gpt-4o-mini` has no results on `examples/` (it would need API spend), and `clinic-desk` has no ground truth in
  `examples/expected.json`.
- **86 cases** give wide intervals; differences within the intervals are not findings.

## 5b. Follow-up experiment: does the model rank drift above clean code? (rules fixed before running, 28 Oct 2026)

The tuned model's answers are 94% COMPLIANT with a flat confidence of 0.9, so they cannot be thresholded. `specdrift_scoring.ipynb` (not in the repo; it embeds
third-party training records) reads the probability of the first answer token (DRIFT, COMPLIANT or UNCERTAIN) for every rule check, with the adapter on and off,
and ranks the checks by P(DRIFT). Nothing is generated or trained. It is run on the **run-3 adapter** (the one R1 scored); the notebook checks the weights'
fingerprint (sha256 starting `d9f9f98e24abcf0b`) and stops if another adapter is attached.

- **Truth:** the benchmark's own per-rule truth over the same 1,106 rule checks as the comparison report (64 truly violated).
- **Threshold t*:** chosen on the validation set only, as the lowest P(DRIFT) at which the validation false-alarm rate (COMPLIANT examples) is at most 0.10, then
  applied unchanged to the 86 cases. Other thresholds are shown but are exploratory because they look at the benchmark.
- **AUC reading (my proposal, not a standard):** 0.8 or more on the benchmark means usable signal hidden by the answers; about 0.5 means nothing that transfers.
- **Not tested on a GPU before the run:** the token-level scoring path (the plumbing, truth, AUC and threshold code were tested locally with a fake scorer).

**TO FILL** after the run: validation and benchmark AUC (tuned and untuned) with intervals, recall and false-alarm at t*.

## 6. Not done

Ablations H2 and H3 (mixes `main-v6-nopaper`, `main-v6-noN23`, `main-v6-heldout` and their size-matched controls are built and exported but not
trained), additional seeds, a stronger zero-shot model, the 7B run, a multi-project validation set, and the human spot-check.
