# Prompt for the next Claude Code session

Copy everything between the two lines into a new session opened in
`/Users/nandeshjeya/Documents/Academic/MiniProject/specdrift-bench`.

---

You are continuing a mini-project called SpecDrift-Bench. Read these three files first, in this order, before doing anything else:

1. `docs/handoff.md` (what exists, what was measured, what is still open)
2. `docs/training-data-spec.md` (the plan and the data format)
3. `docs/rule-extraction-prompt.md` (the prompts and gates; sections 11 to 13 hold the pilot results)

Then run `.venv/bin/python -m pytest -q`, `.venv/bin/ruff check specdrift tests scripts` and `.venv/bin/mypy`. All three must be clean (465 tests expected) before you change anything. If they are not, stop and tell me what differs.

## The goal

The panel asked for a trained model. We are fine-tuning a small open code model (Qwen2.5-Coder, QLoRA, on Kaggle) to act as SpecGuard's Stage 2 verifier, and comparing it with the current zero-shot `gpt-4o-mini` on the 86 frozen test cases. The data pipeline is built and piloted on three repos. Your job is to finish the path from "mixed data" to "a measured comparison".

## Ground rules (these came from earlier decisions; keep them)

- **One step at a time, and stop to report after each.** Do not run ahead.
- **Never train on, tune on, or choose thresholds with the 86 cases or the four `examples/` projects.** They are frozen in `data/test_manifest.json`. `specdrift data-check` and `data-mix` enforce this; do not bypass or edit them.
- **Do not run third-party code without my explicit approval.** That includes `scripts/shortlist_repos.py --verify` and any new repo. If a step needs it, tell me the exact command and let me run it with `! <command>`. Do not work around a permission denial.
- **Do not commit to git** unless I ask. Do not rotate, print or log secrets. `.env` holds a real API key; never echo its contents, and do not use the `settings` fixture's key anywhere it can be printed.
- **Do not change the existing chunker's line numbering** (`specdrift/code/chunker.py`, `verify/prompts.py:render_chunk`). Changing it invalidates the cached benchmark results. If you think it should change, say so and let me decide.
- **Every new behaviour gets tests, and every guard gets a mutation check:** disable the guard, confirm a test fails *for the right reason* (not because the code broke), restore the file byte-for-byte, confirm it passes again.
- **Report what did not work, with numbers.** If something fails or a result is weaker than hoped, say so plainly.
- Use `.venv/bin/python -m pytest`, not bare `pytest`.

## Step 1: the human gate (mine, not yours)

`docs/pilot-spot-check.md` lists 18 rules and 8 oracles for me to review. Nothing should be scaled until it passes (at least 90% of rules, 85% of oracles). Do not fill it in yourself: the model that wrote the rules cannot judge them. Ask me for the result. If I report failures, change the prompt in `specdrift/data/rulegen.py`, bump `RULE_PROMPT_VERSION` or `ORACLE_PROMPT_VERSION`, and repeat the pilot before going further. You may do Step 2 while I do this.

## Step 2: build the SFT export

Add `specdrift data-sft`, which turns `data/mix/<name>/train.jsonl` and `val.jsonl` into the exact text the model is fine-tuned on.

Requirements:

- The prompt must be byte-identical to what the detector sends at inference. Build it with `SYSTEM_PROMPT` and `build_user_prompt(rule, chunks)` from `specdrift/verify/prompts.py`; do not re-implement it. Record `PROMPT_VERSION` in the output and in a stats file.
- The completion is the JSON the verifier parses: exactly the keys `verdict`, `confidence`, `violated_clause`, `evidence` (`file`, `start_line`, `end_line`), `counterexample` (`input`, `expected`, `actual`). It must round-trip through `parse_response` and the evidence bar in `specdrift/verify/verifier.py` without being downgraded. Test this on every example in the pilot mix.
- Emit a chat-style file (`messages`: system, user, assistant) and a plain `prompt`/`completion` file, with a note that loss must be computed on the completion only.
- Report token counts (use the target model's tokenizer if available offline, otherwise state the estimate method), the share of examples over 1,536 tokens, and the label and category mix.
- Prove there is no train/serve skew: a test that builds an example's prompt through the SFT path and through `verify_rule`'s path and asserts they are equal.
- Do not put the label, category, provenance or mutation operator anywhere in the prompt.

Stop and show me the stats before continuing.

## Step 3: evaluation harness (no GPU needed)

1. Add a Hugging Face / local provider to `specdrift/verify/llm.py` so a fine-tuned adapter can be used as the Stage 2 model. Follow the existing `Completer` protocol and `.env` conventions (`LLM_PROVIDER`, `LLM_MODEL`). It must work offline for tests (use a fake) and must not require torch to import.
2. Write a Kaggle notebook as a plain script under `scripts/kaggle/` (do not run it): QLoRA on Qwen2.5-Coder-1.5B-Instruct first, fp16 (T4 has no bf16), LoRA r=16, alpha=32, dropout 0.05, all linear layers, LR 2e-4 cosine, effective batch 16, loss on the completion only, checkpoint every 200 steps to `/kaggle/working`, secrets from Kaggle Secrets only. Include the pilot go/no-go check from the spec: the fine-tuned 1.5B must beat the untuned 1.5B on validation false-alarm rate before 7B is attempted.
3. Write the comparison script that, once an adapter exists, runs all detectors on the 86 cases (3 runs) and on the four `examples/` projects, and reports per-category recall, precision, strict precision, false-alarm rate, UNCERTAIN rate, bootstrap 95% CIs (use `specdrift stability`), plus the abstention coverage-vs-accuracy curve and calibration error.

Stop and report.

## Step 4: scale the data (needs my decisions first)

Ask me, and wait for answers, before doing any of this:

- Which model should generate rules and oracles? It must **not** be `gpt-4o-mini` (the baseline detector). I may say "you, interactively" again.
- Whether to spend API money on my key, and an upper bound.
- Which of the 15 repos with unresolved licences I have read and approve (`data/repos.csv`, reason column).

Then, for the 8 verified repos not yet piloted (`pyflakes`, `tabulate`, `schema`, `xmltodict`, `iniconfig`, `flashtext`, `colorama`, `tomli`; check `data/repos_verified.csv`), repeat the pilot recipe from `docs/rule-extraction-prompt.md`: prompt A, lint, prompt B, static oracle gate, `data-inject --focus-rules`, `data-inject --benign`, `data-assemble`, `data-check`, then `data-mix`. Cloning and running them needs my approval as above.

## Step 5: the mix and the first real training run

Re-run `data-mix` over all pools. Report: examples per split, which label is binding, the share of the largest project, and whether the held-out validation project is still sensible. Build the ablation mixes the spec lists: no Stage A (H3), no N2/N3 (H2), and `--exclude-operator` for the benchmark-overlapping families (`rename_local`, `extract_temp`, `decoy_comment`, `decoy_docstring`). Export each with `data-sft`. Tell me which Kaggle runs to launch, in order, and what result would make you stop.

## Known open problems (do not hide these)

- The pilot mix (414 train examples, 3 repos) is a rehearsal, not a training set. Do not draw model conclusions from it.
- N2/N3 and DRIFT labels are only as good as the oracles; the spot-check is the only check on that.
- Retrieval misses the right method in many-method classes, so about 23% of Stage B is UNCERTAIN against a 10% target. Decide with me whether to cap it in the mix or to raise `--gold-view`.
- Popular libraries are probably in the base model's pretraining data. Report each repo's star count as a threat to validity.
- The paper's HumanEval, MBPP and QuixBugs data is likely in the pretraining data of Qwen too.

When you finish a step, give me: what you built, the exact commands, the test count, the numbers, what surprised you, and what you recommend next. Then stop.

---
