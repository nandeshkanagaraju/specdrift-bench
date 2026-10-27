# SpecDrift-Bench: hand-over summary (as of 26 Oct 2026)

Paste this into a new Claude Code session opened in `/Users/nandeshjeya/Documents/Academic/MiniProject/specdrift-bench`.

## Why this work exists

SpecDrift-Bench is a mini-project: a benchmark plus a detector (SpecGuard) that checks whether code still matches a numbered specification. The Review 2 score was 13/30; the remark was "Evaluate the model properly".
The panel wants a **trained** model. Stage 2 of SpecGuard is currently `gpt-4o-mini`, zero-shot. On the 86 hand-built cases it has recall 0.54, precision 0.65, strict precision 0.29, false-alarm rate 0.63 (it flags 63% of clean controls).
That matches the over-correction bias in Jin & Chen (ASE 2026, `s10515-026-00638-5.pdf`).

## The plan

Fine-tune a small open code model as the Stage 2 verifier (QLoRA on Kaggle, 2xT4 or P100, about 30 GPU hours a week): Qwen2.5-Coder-1.5B as a pilot, then 7B only if the pilot shows signal. Optionally fine-tune the retriever and calibrate the UNCERTAIN threshold.
Hypotheses: **H1** fine-tuned beats zero-shot on false alarms at equal recall; **H2** hard negatives are what cut false alarms; **H3** the paper's function-level data transfers to project-level drift.
Evaluate on the 86 frozen cases plus the four unseen projects in `examples/` (`auth-gateway`, `clinic-desk`, `shop-checkout`, `task-queue`), 3 runs, bootstrap 95% CIs, against: zero-shot `gpt-4o-mini`, a stronger zero-shot model, the untuned open model, and the fine-tuned one.
The design documents are `docs/training-data-spec.md` (the plan and data format), `docs/rule-extraction-prompt.md` (prompts, gates, measured pilot results in sections 11 to 13), and `docs/pilot-spot-check.md` (human review sheet).

## What exists (all in `specdrift/data/`, tests in `tests/`; 465 tests pass; ruff and mypy clean; nothing committed to git)

Run tests with `.venv/bin/python -m pytest` (plain `pytest` fails to import two older test files).

| Piece | Command | Notes |
| --- | --- | --- |
| Stage A converter | `data-stage-a` | Paper data to 1,072 examples (398 DRIFT, 674 COMPLIANT), labels checked by running the paper's tests; `data/stage_a.jsonl` |
| Leakage checker | `data-freeze`, `data-check` | Freezes the 86 cases, host projects and `examples/` into `data/test_manifest.json`; checks projects, chunks, rules, injections, 13-grams |
| Injector | `data-inject` | Sandboxed (`sandbox-exec`: no network, scratch-only writes); 16 drift operators; `--focus-rules` mutates only cited lines; `--benign` generates N2/N3 |
| Assembler | `data-assemble` | Labels by per-rule **oracle tests**; real Stage 1 retrieval view; UNCERTAIN on retrieval miss plus a gold-view DRIFT recovery; N1/N2/N3/wrong-rule negatives |
| Rule/oracle pipeline | `data-rulegen-prompt`, `-render`, `data-oracle-prompt`, `-check` | Model returns JSON; code renders `spec.md` and `rules.yaml`; lint plus a static oracle gate |
| Validator | `specdrift/data/validate.py` | Run inside the assembler and mixer |
| Mixer | `data-mix` | Splits by project; per-rule cap; 60% max share per project; 35/55/10 label shares; checks leakage before writing |
| Repo shortlist | `scripts/shortlist_repos.py`, `scripts/repo_seeds.txt` | API-only by default; `--verify` clones and runs tests (executes third-party code) |

`tests/fixtures/toyshop/` is a small project with hand-written oracles, used by the tests.

## Results so far

- **Repo verification:** 30 shortlisted, 11 passed 3-of-3 sandboxed runs (`python-semver`, `cachetools`, `pyflakes`, `tabulate`, `schema`, `voluptuous`, `xmltodict`, `iniconfig`, `flashtext`, `colorama`, `tomli`); the 19 failures needed test-only dependencies. 15 repos have unresolved licences (GitHub reported NOASSERTION) and need a human to read their LICENSE files.
- **Pilot on 3 repos** (semver, cachetools, voluptuous): 57 rules and 57 oracles. **Claude wrote them interactively, acting as the generator model, not through an API**, so lint-drop rates are indicative. Outputs are in `data/pilot/`.
- **Injector coverage:** an operator can change the cited line of 54 of 57 rules; 43 of 57 rules have a DRIFT example (173 DRIFT in total).
- **N2/N3:** 327 verified behaviour-preserving examples (142 N2, 185 N3).
- **Mix `data/mix/pilot-v1`:** 414 train / 162 val, shares 35/55/10, validation project `cachetools`, leakage check clean. Variants: `pilot-v1-heldout` (benchmark-overlapping operator families excluded) and `pilot-v1-nopaper`.
- This is a rehearsal of the pipeline, **not** a training set: far too small to fine-tune on.

## Findings and defects worth remembering

- Edit distance cannot de-duplicate rules (opposite rules one word apart); duplicates are now defined by identical symbols plus the same cited line.
- The "oracle must kill a mutant" gate gave false alarms and is now report-only; targeted hand-mutation of the rule's own behaviour showed the oracles were sound.
- `decoy_dead_branch` before an `elif` rewired the chain; fixed, and the assembler never turns a non-preserved N2/N3 mutant into any example.
- **Not fixed on purpose:** the existing chunker numbers the module chunk consecutively although it drops blank lines between statements, so a constant on file line 6 is shown to the model as line 4. Changing it would invalidate the benchmark's cached results. Training evidence uses the numbers the prompt shows.
- Retrieval with the local hashing embedder misses the right method in many-method classes (semver `Version`), which drives a 23% UNCERTAIN share against a 10% target.

## Not done yet, in priority order

1. **Human spot-check** of `docs/pilot-spot-check.md` (18 rules, 8 oracles; need at least 90% of rules and 85% of oracles to pass). The model that wrote the rules cannot do this. Every DRIFT label depends on the oracles, so nothing should scale before it passes.
2. **SFT export:** convert `train.jsonl` and `val.jsonl` to exact prompt/completion text (`verify/prompts.py` system prompt plus `build_user_prompt`, JSON target) for the Kaggle run.
3. **Scale** to the other 8 verified repos; choose a rule/oracle generator model that is **not** `gpt-4o-mini`.
4. Add a Hugging Face provider in `specdrift/verify/llm.py`, fine-tune on Kaggle, run the full evaluation.
5. Decide whether to fix the chunker numbering and re-run the benchmark.

## Things to know about this environment

- `.env` holds a real OpenAI key. A test failure once printed the first characters of `llm_api_key` (the `settings` test fixture loads the real `.env`). **Rotate it before sharing any transcript.**
- Running third-party code (the repo `--verify` step) is blocked by the auto-mode safety classifier unless the user approves; the user can run it with `! <command>`. Unquoted shell variables in `rm` are also blocked; do not work around either.
- Downloaded repos belong in their own scratch directory; data derived from them (`data/**/*.jsonl`, prompts) is gitignored because the paper's repo has no licence file.
- The user prefers one deliverable per step, each with tests, a check that disabling each guard makes a test fail, and honest reporting of what did not work. They use they/them pronouns.
