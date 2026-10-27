# SpecDrift-Bench: Training Data Specification (Review 3)

Status: plan. Nothing in this document is implemented yet.
Panel remark this answers (Review 2, 13/30): *"Evaluate the model properly."*

## 1. Goal and hypotheses

Today Stage 2 of SpecGuard is `gpt-4o-mini`, zero-shot. Nothing is trained. The measured weakness is
false alarms: 0.63 false-alarm rate and 0.29 strict precision on 86 cases. This matches the
over-correction bias Jin & Chen (ASE 2026) report.

We train a small open code model as the Stage 2 verifier and test three hypotheses:

| ID | Hypothesis | Decided by |
| --- | --- | --- |
| H1 | A fine-tuned open model has a lower false-alarm rate than zero-shot `gpt-4o-mini` at equal or better recall | 86-case test set, 3 runs, bootstrap CI |
| H2 | Hard negatives (refactors, benign decoys) are what reduce false alarms | Ablation: train with and without them |
| H3 | Function-level paired data (Jin & Chen) transfers to project-level drift | Ablation: with and without Stage A data |

A negative result on H1 is still reported. The deliverable is a properly measured comparison.

## 2. The task the model learns

One example is one (rule, retrieved excerpts) pair. This is exactly what `verify/prompts.py`
builds today (`SYSTEM_PROMPT` + `build_user_prompt`, `PROMPT_VERSION = "v1"`). The model
must emit the same JSON as the `Verdict` schema: `verdict`, `confidence`, `violated_clause`,
`evidence`, `counterexample`.

Training reuses `render_chunk` and `build_user_prompt` unchanged, so there is no train/serve skew.
If the prompt changes, bump `PROMPT_VERSION` and regenerate the data.

## 3. Training example schema (JSONL, one object per line)

```json
{
  "example_id": "synth-flask-todo-0412-R07",
  "source": "paper | synth | hardneg",
  "split": "train | val",
  "project_id": "flask-todo",
  "rule": {"id": "R07", "text": "Borrowing MUST raise `LoanLimitExceeded` when ..."},
  "chunks": [
    {"id": "src/x.py::Service.borrow", "file": "src/x.py", "qualname": "Service.borrow",
     "start_line": 31, "end_line": 52, "source": "..."}
  ],
  "label": "DRIFT | COMPLIANT | UNCERTAIN",
  "category": "D1..D9 | N1..N3 | paper:<bug_type>",
  "target": {
    "verdict": "DRIFT",
    "confidence": 0.9,
    "violated_clause": "exact quote from rule.text",
    "evidence": {"file": "src/x.py", "start_line": 40, "end_line": 41},
    "counterexample": {"input": "...", "expected": "...", "actual": "..."}
  },
  "provenance": {
    "label_method": "execution | test_suite | injected_known | human",
    "generator": "mutmut | injector-v1 | humanevalpack | quixbugs | mbpp-buggy",
    "oracle_test": "path or null",
    "gen_model": "model id or null",
    "seed": 17
  }
}
```

Rules for the file:

- `target` is the supervised output. For `COMPLIANT` and `UNCERTAIN`, `violated_clause` is `""`
  and `evidence`/`counterexample` are empty, as in the current prompt.
- `violated_clause` must be a verbatim substring of `rule.text`. `evidence` lines must fall inside a retrieved chunk.
  The validator in section 8 rejects anything else.
- `UNCERTAIN` examples are built by dropping the relevant chunk, so the correct answer is to abstain.
  This is how the abstention route is trained. Target share: 8 to 10 percent.
- `confidence` in `target` is set from the label method: 0.9 for execution-verified, 0.7 for test-suite-only.
  It is calibrated afterwards (section 7), not trusted.

## 4. Data sources and mix

| Stage | Source | Level | What it supplies | Label method | Target size |
| --- | --- | --- | --- | --- | --- |
| A | Jin & Chen paired data (HumanEval-X-Bugs, Buggy-MBPP, QuixBugs) | function | requirement -> rule, function -> chunk; canonical = COMPLIANT, buggy = DRIFT; `bug_type` maps to D-categories | benchmark tests | about 1,000 after filtering (1,474 raw) |
| B | Synthetic project-level (section 5) | project | rules from real repos, injected drift D1-D9, matched clean code | execution | 6,000 to 10,000 |
| C | Hard negatives (section 6) | project | N2 refactors, N3 benign decoys, N1 unchanged | execution (suite must pass) | 30 to 40 percent of B |
| D | Abstention examples | project | relevant chunk removed -> UNCERTAIN | by construction | 8 to 10 percent of B |

Target class balance for the final training mix: DRIFT about 35 percent, COMPLIANT about 55 percent,
UNCERTAIN about 10 percent. The reason for skewing toward COMPLIANT is that the production failure
is false alarms, and real code is mostly compliant.

Stage A data audit (run on the public repo, 24 Oct 2026): 737 tasks, so 1,474 instances. The buggy side is noisy:

| File | Tasks | Buggy code that parses | Buggy identical to canonical |
| --- | ---: | ---: | ---: |
| humaneval | 164 | 162 | 0 |
| mbpp | 533 | **252** | **11** |
| quixbugs | 40 | 40 | 0 |

More than half of the MBPP buggy solutions do not compile, apparently from reconstructed prefixes with mismatched indentation. A model would
learn "syntax error means DRIFT", which is a shortcut and not drift detection. Stage A filter: keep a buggy example only if it parses and differs from the
canonical solution after whitespace normalisation, and keep canonical examples only if they parse. Built and run (`specdrift data-stage-a`): **1,072 examples (398 DRIFT, 674 COMPLIANT)** from 737 tasks, with labels checked by running each task's tests
(correct side must pass, buggy side must fail) and every DRIFT counterexample taken from a real failing assert. HumanEval 301, MBPP 760, QuixBugs 11. QuixBugs is almost gone
because 33 of its 40 tasks have empty tests, so it cannot back either label. Weak spot: the paper has no per-clause annotation, so `violated_clause` is the requirement's first sentence
(`provenance.notes.clause_method`); if the model learns to always quote the first sentence, the Stage B data (real clauses) must correct it, and the H3 ablation will show it.
The repo has no LICENSE file, so use it for research training only, do not redistribute the derived JSONL, and cite the paper.

Stage A caveat: the paper's examples are single functions with a docstring-style requirement. They teach
"does this function do what this sentence says" and are weak on multi-file context, ordering, and
scope creep. Treat A as warm-up (first epoch), not the core.

Contamination caveat: HumanEval, MBPP and QuixBugs are likely in Qwen's pretraining data. Report this
as a threat to validity and show that the Stage-A ablation (H3) does not change the conclusion.

## 5. Synthetic generator (Stage B)

Pipeline per repo:

1. **Select repos.** Python, permissive licence (MIT, BSD, Apache-2.0), 300 to 3,000 lines of source, a passing
   test suite, no network or database needed at test time. Target 25 to 40 repos. Record URL, commit SHA and licence in
   `data/repos.csv`. Discard repos whose suite is flaky (fails once in 3 runs).
2. **Extract rules.** An LLM reads the code and README and writes a `spec.md` in the same format as `projects/*/spec.md`:
   numbered, atomic, one MUST/MUST NOT clause each. Reject rules that do not name a concrete value, error or ordering.
   Spot-check 10 percent by hand.
3. **Map rules to code.** Record `gold_symbol` per rule (same field the cases already use), then build chunks with the
   existing `code/chunker.py`.
4. **Inject drift.** Two injectors, so the model does not learn one generator's fingerprints:
   - `injector-v1`: template-based D1-D6, D9 patches (`>`/`>=`, constant change, delete a check, weaken `and`/`or`, swap
     two statements, change an exception type or returned shape).
   - `mutmut` / `cosmic-ray` operators filtered to those touching a rule's gold symbol.
   - D7 (comment decoy) and D8 (scope creep): LLM-written, then verified by hand because they cannot be checked by a test.
   Built: `specdrift data-inject <project> --sandbox require` (`specdrift/data/inject.py`) generates D1, D2, D3, D4, D5, D6 and D9 mutants (16 operators; `--focus-rules` mutates only the lines the rules cite) as find/replace
   patches that match their file exactly once, and records `find`/`replace` for the leakage check. It refuses any project under `projects/` or `examples/`.
   Third-party tests run under `sandbox-exec` (no network, writes confined to scratch), and the injector exits instead of running unsandboxed when `--sandbox require` is set.
   Not generated: D7 and D8 (hand-written), and the mapping from mutant to rule (`symbol` is recorded, the rule link comes with rule extraction).
   Labels from the project's own suite: `killed` (assertion failure, a DRIFT candidate), `survived` (unverified, needs an oracle, never DRIFT by default),
   `crash` (NameError, UnboundLocalError, import errors: trivially broken, excluded), `timeout`, `invalid`.
   On the three host projects (read-only, nothing kept): 23 to 35 mutants each, about 55 to 65 percent killed, 30 to 45 percent survived, 1 to 2 crashes.
   Assembler (`specdrift data-assemble <project> --mutants m.jsonl`, `specdrift/data/assemble.py`): a project supplies `rules.yaml` mapping each rule to the code symbols it covers and
   the pytest oracle file that decides it. A mutant is DRIFT for a rule only if that oracle passes on the original and fails on the mutant, so a mutant the project's own suite misses can
   still be rescued (the toy project has two). The view shown is Stage 1's real top-k excerpt with constant context; `--gold-view` of the examples show the changed chunk alone. If the changed
   chunk is not in the view, the label is UNCERTAIN (`abstain:retrieval_miss`), never DRIFT. `--abstain` of the examples also get an UNCERTAIN twin with the rule's code removed.
   The same mutated code shown against a covered rule whose oracle still passes is a COMPLIANT hard negative (`hardneg:wrong_rule`, with `violates_other_rules` recorded); unchanged code is `N1`.
   Counterexamples are read from the failing oracle's traceback. `specdrift/data/validate.py` checks every example and drops (and reports) any that fail.
   Known quirk of the existing chunker, kept as is because changing it would invalidate cached benchmark results: the module chunk joins top-level statements without the blank lines
   between them, but `render_chunk` numbers it consecutively, so a constant on file line 6 is shown as line 4. Evidence in training examples uses the numbers the prompt shows.
5. **Label by execution.** Keep a DRIFT example only if an oracle test derived from the rule passes on the pristine repo and
   fails on the mutant (same standard as `cases/oracles/`). Mutants that the existing suite does not kill need a generated oracle; if
   none can be written, drop the mutant. Never label a mutant DRIFT only because it was injected.
6. **Retrieve like production.** Chunks come from the real Stage 1 retriever at `TOP_K=3`, so the model sees imperfect
   retrieval, not clean gold chunks. Mix in a gold-only view for 20 percent of examples.
7. **Counterexamples.** For DRIFT, run the oracle to obtain the failing input, expected and actual values. These are
   real, not LLM-invented.

## 6. Hard negatives (Stage C)

These carry H2. For each repo, generate on the clean code:

- **N2 refactors**: rename locals, extract helper, reorder independent statements, replace loop with comprehension. The
  suite must still pass, and the oracle must still pass.
- **N3 benign decoys**: add a comment or docstring that mentions a rule number or a suspicious word, with no behaviour change.
- **N1**: untouched code, plain COMPLIANT.
- **Wrong-rule pairing**: show a drifted chunk against a rule it does not affect. Correct label is COMPLIANT. This trains
  the model to stay on the rule it was given and directly targets the strict-precision gap (61 off-target flags).

## 7. Splits and leakage rules (the part the panel will test)

**Test set = the 86 existing cases, frozen.** They are never used for training, validation, prompt tuning or threshold tuning.
The three host projects (`library`, `wallet`, `ratelimiter`) and every file under `projects/` are excluded from all training data.

Splits are by project, never by row:

| Split | Content | Use |
| --- | --- | --- |
| train | about 80 percent of synthetic repos + Stage A train portion | gradient updates |
| val | about 20 percent of synthetic repos (whole repos) | early stopping, prompt choice, abstention threshold, calibration |
| test | the 86 frozen cases | final report only |
| test-2 (new) | the four unseen projects in `examples/` (`auth-gateway`, `clinic-desk`, `shop-checkout`, `task-queue`) with `examples/expected.json`, extended with oracles | generalisation check; answers the README's "until a fourth project confirms" caveat |

Mandatory checks, run by a script and failing the build if violated:

1. No `project_id` appears in more than one split.
2. No train chunk has a normalised-whitespace hash equal to any test or test-2 chunk.
3. No train rule text has a normalised edit distance below 0.2 from any test rule text.
4. No train injection uses the exact `find`/`replace` pair of any test case.
5. The injectors' templates differ from the strings used to author the 86 cases (reviewed once by hand).
6. Report n-gram overlap (13-gram) between train and test chunks. Document the figure.

Built: `specdrift data-freeze` writes `data/test_manifest.json` (fingerprints of the 86 cases, their original and drifted code, the host projects, the four
`examples/` projects and all test rules; commit this file). `specdrift data-check data/*.jsonl` refuses to run if the test set on disk no longer matches the manifest,
then runs checks 1, 2, 3, 4 and 6, and exits 1 on any violation. Chunk comparison ignores comments and layout. Chunks under 15 tokens are ignored, because empty classes
and bare imports match by chance. Check 5 stays manual.

Convention for Stage B: every injected example must record `provenance.notes.inject_find` and `inject_replace`. Without them check 4 cannot apply, and the checker says so in its output
(Stage A reports 1072 of 1072 with no injection record, which is correct: it injects nothing).

N2 and N3 (`specdrift data-inject <project> --benign`, `specdrift/data/benign.py`): the hard negatives. N2 refactors: `rename_local`, `swap_compare_sides`, `not_eq`, `expand_augassign`, `extract_temp`, `reorder_assignments`.
N3 decoys: `decoy_comment`, `decoy_docstring`, `decoy_dead_branch`. A candidate is used only if the project's suite *and* every oracle for the rules covering the changed code still pass; one that breaks either is a generator defect and is skipped, never turned into a DRIFT example.
Wording of the N3 text is checked against every string in `cases/*.yaml` by a test. Each operator is tagged in `OVERLAPS_BENCHMARK` with whether its family also appears in the benchmark's own N2/N3 cases, and
`data-mix --exclude-operator` holds those families out so a held-out-family result can be reported. When retrieval does not show a refactor, the assembler emits a second example that does (`--gold-on-miss`).

Mixer (`specdrift data-mix a.jsonl b.jsonl ... --out data/mix/<name>`, `specdrift/data/mix.py`): turns the pools into `train.jsonl`, `val.jsonl` and a `mix.json` report.
Splits are by project: a Stage B project goes wholly to train or validation (`--val-fraction`, at least one project when there are two or more, or name them with `--val-project`);
Stage A keeps its per-task split. At most `--max-per-rule` examples per (project, rule, label); draws are round-robin across projects and then across mutation operators; no project or Stage A
dataset may supply more than `--max-group-share` (0.6) of any label, and when the others cannot make up the rest the mix *shrinks* instead of being padded from the big project. Label shares default to
35 / 55 / 10 (`--drift`, `--uncertain`); Stage A takes `--paper-share` (0.3, set 0 for the H3 ablation) and has no UNCERTAIN, so Stage B carries the whole UNCERTAIN share. The scarcest label sets the size and is named in the report.
Exact-duplicate content (two runs that mutated the same line) is dropped; every example is re-validated; and the mix is checked against the frozen test set *before anything is written*.

Calibration: fit the `UNCERTAIN` threshold and a temperature on val only. Freeze both before touching test.

## 8. Validator (`specdrift data validate`, to be written)

Per example: JSON parses; `target` matches the `Verdict` schema; `violated_clause` is a substring of the rule; evidence lines fall in a
chunk; DRIFT has a non-empty counterexample; token length of prompt + target is at most 3,072 (raised from 1,536 to 2,048 and then to 3,072 on 26 Oct 2026: iniconfig and tomli lost 142 examples to the first cap and flashtext and xmltodict lost 196 more to the second, mostly the long core functions; examples over the limit are dropped, never truncated);
`label` agrees with `provenance.label_method`; no secrets (scan for `sk-`, `AKIA`, private keys). Emit counts by source, category, label and split.

## 9. Models and training (Kaggle)

| Run | Base | Method | Purpose |
| --- | --- | --- | --- |
| P0 | Qwen2.5-Coder-1.5B-Instruct | QLoRA, 1 epoch on 2k examples | Pipeline smoke test; go/no-go |
| M1 | Qwen2.5-Coder-1.5B-Instruct | QLoRA, full mix | Main small model |
| M2 | Qwen2.5-Coder-7B-Instruct | QLoRA, full mix, `--max-len 1536` (smaller than the 3,072 data limit, so the longer examples are dropped at train time), fp16 | Main model if M1 shows signal |
| Ablations | M1 config | drop Stage A; drop Stage C; no abstention examples; retriever frozen vs fine-tuned | H2, H3 |

Settings to start from: LoRA r=16, alpha=32, dropout 0.05, all linear layers; LR 2e-4 with cosine decay; effective batch 16;
loss on the target tokens only; 1 to 2 epochs; fp16 (T4 has no bf16); save a checkpoint every 200 steps to `/kaggle/working`.
Secrets go in Kaggle Secrets, never in a notebook or dataset. The adapter (tens of MB) is the artefact to download.

## 10. Evaluation protocol

Compared on the same 86 cases and on test-2, 3 runs each, bootstrap 95 percent CI over cases (`specdrift stability`):

1. `gpt-4o-mini` zero-shot (current baseline)
2. one stronger zero-shot model (to show the gap is not just "bigger is better")
3. base Qwen 1.5B and 7B, zero-shot
4. fine-tuned M1 and M2
5. fine-tuned + counterexample-execution filter (the planned Review 3 step, modelled on Jin & Chen's Fix-guided filter)

Metrics, as already defined in the README: per-category recall, precision, strict precision, false-alarm rate, UNCERTAIN rate, Recall@k,
retrieval-vs-reasoning attribution. Add: abstention coverage vs accuracy curve, calibration error (ECE), and the Jin & Chen
rationale audit (share of DRIFT claims whose counterexample is wrong when executed).

Report the table even if H1 fails. State the contamination caveat and the 86-case interval widths next to it.

## 11. Work plan and order

| # | Task | Where | Output |
| --- | --- | --- | --- |
| 1 | Freeze test set; write leakage checker | Mac | `data/test_manifest.json`, `specdrift data check` |
| 2 | Convert Stage A (paper repo) into the schema | Mac | `data/stage_a.jsonl` |
| 3 | Pick repos; extract rules; hand-check sample | Mac | `data/repos.csv`, specs |
| 4 | Injectors, oracle-based labelling, hard negatives, abstention | Mac | `data/stage_bcd.jsonl` |
| 5 | Validator + split + stats | Mac | `data/{train,val}.jsonl`, `data/stats.md` |
| 6 | Upload as private Kaggle Dataset; run P0 | Kaggle | go/no-go |
| 7 | M1, then M2; ablations | Kaggle | adapters, logs |
| 8 | HF-backed provider in `verify/llm.py`; run the 86 cases + test-2 | Kaggle or Mac | new `results/` |
| 9 | Tables, CIs, paper section, Review 3 slides | Mac | report |

Go/no-go after step 6: if P0 does not beat the untuned 1.5B on val false-alarm rate, fix the data (label noise, balance) before spending
the weekly GPU quota on 7B.

## 12. Risks

| Risk | Mitigation |
| --- | --- |
| Injected bugs are easier than the 86 cases (templates leak) | Two injectors, test-2 on unseen projects, hand review of templates |
| LLM-written rules are vague or wrong | Atomic-rule filter, 10 percent manual check, drop low-quality repos |
| Labels wrong when oracle is weak | DRIFT only if oracle fails on mutant; waive otherwise (as with `library-D2-02`) |
| Kaggle weekly quota (about 30 GPU hours) runs out | P0 first; 1.5B as fallback model; checkpoint often |
| Model matches zero-shot, no gain | Report honestly; the ablations still show where the bias comes from |
| Licence of source repos | Record licence per repo; train only on permissive; do not redistribute code, only derived JSONL with SHAs |
| API cost of rule extraction | Cache by content, as the current LLM layer does; one pass per repo |
