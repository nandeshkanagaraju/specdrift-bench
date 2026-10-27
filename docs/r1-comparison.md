# Detector comparison

Mean over runs with bootstrap 95% CI over cases (pooled across runs). DRIFT is the positive class.

## 86 frozen cases

| arm | runs | recall | precision | strict precision | false-alarm rate | UNCERTAIN rate | ECE |
|---|---:|---|---|---|---|---|---|
| gpt-4o-mini-zero-shot | 3 | 0.54 [0.41, 0.66] | 0.64 [0.51, 0.77] | 0.29 [0.22, 0.36] | 0.65 [0.47, 0.83] | 0.06 [0.05, 0.08] | 0.09 [0.07, 0.10] |
| keyword-baseline | 1 | 0.08 [0.02, 0.16] | 0.33 [0.10, 0.60] | 0.16 [0.04, 0.29] | 0.37 [0.19, 0.56] | 0.00 [0.00, 0.00] | 0.08 [0.07, 0.10] |
| qwen2.5-coder-1.5b-untuned | 1 | 0.42 [0.31, 0.56] | 0.49 [0.35, 0.63] | 0.09 [0.06, 0.11] | 0.96 [0.88, 1.00] | 0.65 [0.61, 0.69] | 0.73 [0.71, 0.76] |
| qwen2.5-coder-1.5b-sft-r0 | 1 | 0.08 [0.02, 0.16] | 1.00 [1.00, 1.00] | 0.50 [0.22, 0.78] | 0.00 [0.00, 0.00] | 0.05 [0.04, 0.07] | 0.05 [0.04, 0.06] |

## Paired difference against `gpt-4o-mini-zero-shot` (arm minus baseline, same cases)

| arm | false-alarm rate | reading | recall | reading |
|---|---|---|---|---|
| keyword-baseline | -0.28 [-0.6471, 0.0833] | no detectable difference (interval includes 0) | -0.46 [-0.5965, -0.3041] | lower (interval excludes 0) |
| qwen2.5-coder-1.5b-untuned | +0.31 [0.1449, 0.4933] | higher (interval excludes 0) | -0.12 [-0.2606, 0.0339] | no detectable difference (interval includes 0) |
| qwen2.5-coder-1.5b-sft-r0 | -0.65 [-0.8333, -0.4691] | lower (interval excludes 0) | -0.46 [-0.5897, -0.3121] | lower (interval excludes 0) |

H1 asks for a lower false-alarm rate at equal or better recall. These rows state what each interval shows; they are not a significance test of H1.


## Per category (drift: recall, control: false-alarm rate)

| category | n | gpt-4o-mini-zero-shot | keyword-baseline | qwen2.5-coder-1.5b-untuned | qwen2.5-coder-1.5b-sft-r0 |
|---|---:|---|---|---|---|
| D1 (recall) | 8 | 0.29 [0.08, 0.54] | 0.12 [0.00, 0.38] | 0.25 [0.00, 0.50] | 0.12 [0.00, 0.38] |
| D2 (recall) | 9 | 1.00 [1.00, 1.00] | 0.22 [0.00, 0.56] | 0.44 [0.11, 0.78] | 0.00 [0.00, 0.00] |
| D3 (recall) | 6 | 0.33 [0.00, 0.67] | 0.17 [0.00, 0.50] | 0.33 [0.00, 0.67] | 0.33 [0.00, 0.67] |
| D4 (recall) | 6 | 1.00 [1.00, 1.00] | 0.00 [0.00, 0.00] | 0.50 [0.17, 0.83] | 0.00 [0.00, 0.00] |
| D5 (recall) | 6 | 0.33 [0.00, 0.67] | 0.00 [0.00, 0.00] | 0.33 [0.00, 0.67] | 0.00 [0.00, 0.00] |
| D6 (recall) | 6 | 0.33 [0.00, 0.67] | 0.00 [0.00, 0.00] | 0.17 [0.00, 0.50] | 0.00 [0.00, 0.00] |
| D7 (recall) | 6 | 0.61 [0.28, 0.94] | 0.00 [0.00, 0.00] | 0.67 [0.33, 1.00] | 0.33 [0.00, 0.67] |
| D8 (recall) | 6 | 0.17 [0.00, 0.50] | 0.17 [0.00, 0.50] | 0.50 [0.17, 0.83] | 0.00 [0.00, 0.00] |
| D9 (recall) | 6 | 0.67 [0.33, 1.00] | 0.00 [0.00, 0.00] | 0.67 [0.33, 1.00] | 0.00 [0.00, 0.00] |
| N1 (false_alarm_rate) | 3 | 0.67 [0.00, 1.00] | 0.33 [0.00, 1.00] | 1.00 [1.00, 1.00] | 0.00 [0.00, 0.00] |
| N2 (false_alarm_rate) | 18 | 0.67 [0.44, 0.89] | 0.33 [0.11, 0.56] | 1.00 [1.00, 1.00] | 0.00 [0.00, 0.00] |
| N3 (false_alarm_rate) | 6 | 0.61 [0.28, 0.94] | 0.50 [0.17, 0.83] | 0.83 [0.50, 1.00] | 0.00 [0.00, 0.00] |

## Abstention: coverage against accuracy

Raise the confidence threshold and an answer below it becomes an abstention. Per (case, rule) pair; recall and false-alarm rate are against all pairs. Full curves are in comparison.json.

**gpt-4o-mini-zero-shot** (3318 pairs)

| threshold | coverage | accuracy | recall | false-alarm rate |
|---:|---:|---:|---:|---:|
| 0.00 | 0.94 | 0.90 | 0.53 | 0.08 |
| 0.90 | 0.94 | 0.90 | 0.53 | 0.08 |
| 1.00 | 0.85 | 0.98 | 0.24 | 0.00 |

**keyword-baseline** (1106 pairs)

| threshold | coverage | accuracy | recall | false-alarm rate |
|---:|---:|---:|---:|---:|
| 0.00 | 1.00 | 0.92 | 0.06 | 0.03 |
| 0.50 | 1.00 | 0.92 | 0.02 | 0.03 |
| 0.67 | 0.92 | 0.95 | 0.00 | 0.00 |
| 0.75 | 0.88 | 0.95 | 0.00 | 0.00 |
| 0.83 | 0.70 | 0.95 | 0.00 | 0.00 |
| 1.00 | 0.45 | 0.96 | 0.00 | 0.00 |

**qwen2.5-coder-1.5b-untuned** (1106 pairs)

| threshold | coverage | accuracy | recall | false-alarm rate |
|---:|---:|---:|---:|---:|
| 0.00 | 0.35 | 0.07 | 0.42 | 0.35 |
| 0.75 | 0.35 | 0.07 | 0.42 | 0.35 |
| 0.80 | 0.34 | 0.07 | 0.42 | 0.34 |
| 0.90 | 0.00 | 0.25 | 0.02 | 0.00 |
| 1.00 | 0.00 | 0.00 | 0.00 | 0.00 |

**qwen2.5-coder-1.5b-sft-r0** (1106 pairs)

| threshold | coverage | accuracy | recall | false-alarm rate |
|---:|---:|---:|---:|---:|
| 0.00 | 0.95 | 0.95 | 0.08 | 0.00 |
| 0.90 | 0.95 | 0.95 | 0.08 | 0.00 |

## Unseen projects (test-2), per rule

| arm | runs | recall | precision | false-alarm rate | UNCERTAIN rate | ECE |
|---|---:|---|---|---|---|---|
| qwen2.5-coder-1.5b-untuned | 1 | 0.30 [0.00, 0.60] | 0.25 [0.00, 0.50] | 0.38 [0.18, 0.57] | 0.65 [0.47, 0.79] | 0.56 |
| qwen2.5-coder-1.5b-sft-r0 | 1 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.08 [0.00, 0.21] | 0.24 [0.12, 0.38] | 0.28 |

Scored projects: auth-gateway, shop-checkout, task-queue (34 rules, 10 drifted).

## Read this before quoting a number

- The curve and ECE use a per-pair truth (DRIFT only for the rules an injection targeted); a non-target rule of a drifted file may really be broken, which makes those numbers slightly pessimistic. D8 and reverse verdicts are left out.
- Confidence is taken to be confidence in the stated verdict; the prompt does not define it further.
- Test-2 ground truth is the authors' claim in examples/expected.json with no oracle test, covers 3 of the 4 projects, and has few rules, so its intervals are wide.
- HumanEval, MBPP and QuixBugs are likely in the pretraining data of the Qwen base models (training-data-spec, section 4).
- keyword-baseline: 1 run(s) of the 86 cases; the plan is 3, so run-to-run spread is thin
- qwen2.5-coder-1.5b-untuned: 1 run by design (greedy decoding is deterministic); the CI covers case sampling only, not training-seed variation
- qwen2.5-coder-1.5b-sft-r0: 1 run by design (greedy decoding is deterministic); the CI covers case sampling only, not training-seed variation
