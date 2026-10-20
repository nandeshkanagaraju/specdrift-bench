# SpecDrift-Bench

A benchmark that measures how reliably a tool notices when code stops matching its
specification — per drift category, with false alarms counted as seriously as misses.

Two things share one package. **SpecDrift-Bench** is the benchmark and the evaluation
framework. **SpecGuard** is the detector under test: Stage 1 retrieves the code a rule
is about, Stage 2 asks a model whether that code still implements it.

The positive class is **drift**. Verdicts are `COMPLIANT`, `DRIFT` or `UNCERTAIN`.

## What is in the box

| | |
| --- | --- |
| Host projects | 3 working Python projects (`library`, `wallet`, `ratelimiter`), 13–14 numbered rules each, one test per rule |
| Cases | 86 labelled cases: 59 drift across 9 categories, 27 negative controls across 3 |
| Detectors | `specguard` (retrieval + verification), `reverse` (code to rules, for scope creep), `specguard-reverse` (both directions), `keyword` (vocabulary matching), `wholefile` (one prompt, whole codebase) |
| Outputs | Per-category recall and false-alarm rate, Recall@k, retrieval-vs-reasoning attribution, an HTML report, and a web dashboard |

Every drift case records `escapes_tests`: whether the host project's own test suite
still passes after the injection. On this dataset **22% of drift survives the tests**,
and unauthorised scope creep (D8) survives 100% of the time — the tests were written
before the behaviour existed, so they cannot fail on it.

### Are the drift labels real?

`escapes_tests` only says the host project's own suite still passes. It cannot tell a
genuine spec violation from a patch that changed nothing observable. So each of the 13
drift cases that escape the tests has an **oracle** in `cases/oracles/<case_id>.py`: a
small pytest file stating the spec's behaviour, which must pass on the pristine project
and fail on the drifted one. `specdrift oracles` checks all 13.

**12 of 13 are confirmed.** The exception, `library-D9-02` (rounding mode changed from
half-up to truncation), is waived with a reason in `cases/oracles/waivers.yaml`:
R13 names no rounding mode, and 0.50 per whole day is always exactly two decimal places,
so both modes return identical values for every input the service can produce. It is a
code change, not a spec violation, and should be read as an unconfirmed label.

## Results so far

Each detector over all 86 cases, `gpt-4o-mini`, temperature 0; the table shows run 1. The
intervals below it show how far to trust it. These numbers are the reason the project
exists rather than a claim about how good any of these detectors is.

| Detector | Precision | Strict precision | Recall | F1 | False-alarm rate | Uncertain | LLM calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| specguard (retrieval + verification) | 0.65 | 0.29 | 0.54 | 0.59 | 0.63 | 0.06 | 252 |
| wholefile (one prompt, whole codebase) | 0.91 | 0.83 | 0.17 | 0.29 | 0.04 | 0.01 | 86 |
| keyword (vocabulary matching) | 0.33 | 0.16 | 0.08 | 0.14 | 0.37 | 0.00 | 0 |

Precision counts only false alarms on negative controls. **Strict precision** also counts
every flag on a rule the injection did not target (61 for specguard), so it is the better
guide to how noisy a detector is.

### How much to trust these numbers

Specguard was run three times (run 1 from the cache, runs 2 and 3 with fresh model calls),
and the other detectors once. Intervals are bootstrap 95% over cases, resampling cases
with replacement and pooling every run's outcome for each one (`specdrift stability`).

| Detector | Runs | Recall (95% CI) | Precision (95% CI) | False-alarm rate (95% CI) |
| --- | ---: | --- | --- | --- |
| specguard | 3 | 0.54 [0.41, 0.66] | 0.64 [0.51, 0.77] | 0.65 [0.47, 0.83] |
| wholefile | 1 | 0.17 [0.08, 0.27] | 0.91 [0.70, 1.00] | 0.04 [0.00, 0.12] |
| keyword | 1 | 0.08 [0.02, 0.16] | 0.33 [0.10, 0.60] | 0.37 [0.19, 0.56] |

- **The model is nearly deterministic here; the case set is the noise.** Across specguard's
  three runs recall did not move at all and the run-to-run standard deviation of the other
  metrics is at most 0.02. Only 5% of cases changed outcome between runs. The width of the
  intervals comes almost entirely from having 86 cases, not from sampling variance in the
  model. The wholefile and keyword intervals cover case sampling only.
- **The ranking of recall is solid; the ranking of precision is not.** Specguard's recall
  interval ([0.41, 0.66]) sits clear of wholefile's ([0.08, 0.27]) and keyword's. Specguard's
  and keyword's precision intervals overlap, and so do specguard's and wholefile's.
- **Per-category differences are mostly not significant.** Categories hold 3–9 cases. Only
  D2 and D4 (every case caught in every run) are clearly separated from the rest; the
  intervals for D1, D3, D5, D6, D8 and D9 are 0.3–0.7 wide and overlap each other. Treat
  the category table as a description of this dataset, not a ranking of failure modes.
  N1 has three cases, so its false-alarm rate (0.67) has an interval of [0.00, 1.00].

Three-run means differ slightly from the single-run table above (specguard precision
0.64 against 0.65, false-alarm rate 0.65 against 0.63) because the table shows run 1.

The two LLM detectors fail in opposite directions. Retrieval more than triples recall
(0.54 against 0.17) — showing the model a short, relevant excerpt is what lets it see a
violation at all. It also makes the detector far noisier: SpecGuard flags 63% of the
negative controls, including two thirds of the semantics-preserving refactors. The
whole-file prompt is quiet and precise but blind, missing four categories outright.

That blindness is not a budget artefact. The whole-file prompt answers every rule in one
reply, so its 6000-token output cap was a suspect, but all 172 cached whole-file responses
(annotated and stripped runs) answered all 13 or 14 rules, the longest at about 900
tokens, and no verdict came from a missing rule or a provider error. The model simply
said COMPLIANT: 1125 of 1146 verdicts. What this comparison does not isolate is
*prompt shape*: whole-file asks for every rule at once, while specguard asks one rule per
call about a short excerpt.

Per category, SpecGuard is strongest exactly where a rule states something checkable —
constants (D2, 100%) and weakened conditions (D4, 100%) — and weakest on ordering (D5,
33%) and error handling (D6, 33%), which need the model to reason about sequence rather
than to compare a value.

### Do the rule-id comments leak the answer?

The host projects annotate code with the rule it implements (`# R12`, `R09 - ...`), which
real code does not. To test whether that inflates the results, every detector was re-run
on copies of the code with the ids removed and the explanations kept
(`STRIP_RULE_IDS=true RESULTS_DIR=results_noids specdrift run ...`; see `bench/ablate.py`).
Single run each, compared with run 1 above:

| Detector | Recall with ids | Recall without | False-alarm rate with | Without |
| --- | ---: | ---: | ---: | ---: |
| specguard | 0.54 | 0.58 | 0.63 | 0.67 |
| wholefile | 0.17 | 0.20 | 0.04 | 0.00 |
| keyword | 0.08 | 0.20 | 0.37 | 1.00 |

**The LLM detectors do not depend on the annotations.** Specguard's recall moved by 0.04,
well inside its interval, and its retrieval misses went from 11 to 9. **The keyword baseline
does:** without ids it flags every negative control, because a `# R12` comment used to make
a rule stating 12 look satisfied. Its original numbers partly reflect that artefact.

### The reverse direction: catching scope creep (D8)

SpecGuard goes rule to code, so it cannot see behaviour no rule mentions: that code is
similar to no rule, and no rule's retrieval ever surfaces it. `verify/reverse.py` goes the
other way. For every function and method it shows the model the whole rule list and asks
whether everything the function does is described or presupposed by some rule.

Two things keep it honest. A finding must **quote, verbatim, the code that carries out the
extra behaviour**; a quote that is not in the function is downgraded to `UNCERTAIN`, and the
quote's real line numbers become the evidence. And a function **identical to one already
reported on the pristine project is treated as accepted**, as with a static-analysis
baseline file, because real specifications leave things out (the wallet spec mentions frozen accounts
but never says how one is frozen) and the checker would otherwise report that gap on every case.

| Detector (3 runs) | D8 recall (95% CI) | Overall recall | False-alarm rate |
| --- | --- | --- | --- |
| `specguard` (forward only) | 0.17 [0.00, 0.50] | 0.54 [0.41, 0.66] | 0.65 [0.47, 0.83] |
| `reverse` alone | 0.78 [0.44, 1.00] | 0.08 [0.02, 0.16] | 0.07 [0.00, 0.17] |
| `specguard-reverse` | 0.78 [0.44, 1.00] | 0.61 [0.48, 0.73] | 0.67 [0.48, 0.85] |

**What this shows.** The reverse pass finds the scope creep the forward pass cannot, and by
itself it is quiet: in run 1, 2 false alarms on 27 clean controls, both on the benign-decoy cases
whose planted comment makes ordinary code look suspicious. Combined, overall recall rises
from 0.54 to 0.61, but the intervals overlap, so that rise is not established; the D8 gain is
the finding, and with six D8 cases even it is suggestive rather than conclusive (the
intervals touch between 0.44 and 0.50). The combined false-alarm rate is SpecGuard's, since
the forward pass supplies almost all of it.

**What it does not do.** It missed two of six D8 cases in run 1: a brand-new `renew` method
that the model judged authorised, and an exemption for `internal-` clients hidden inside the
existing `allow`. It audits functions and methods only, so creep expressed as a module-level
constant is out of reach. And the prompt was adjusted once, after seeing what the model
flagged on the three *pristine* projects (11 of 31 functions on the first wording, 3 on the
second, mostly "this method has no checks", which is the absence of behaviour, not extra
behaviour); the D8 cases were not consulted when doing so, but the same three host projects
supply both, so treat the numbers as optimistic until a fourth project confirms them.

### The false alarms are worth reading

Requiring a cited clause and a concrete counterexample removes *unsupported* drift
claims. It does not remove **wrong** ones. Two real examples from the run above, both on
code that was never modified:

- Rule: *"A new bucket MUST start full."* The model reported `bucket_for(...) → tokens = 0.0`.
  The dataclass field is `tokens: float = BURST_LIMIT`; it misread the default.
- Rule: *"An allowed request MUST consume exactly 1 token."* The model's counterexample was
  `tokens 1.5 → 0.5` — which is consuming exactly one token, and so confirms the rule it
  claims is violated.

Both arrived with a quoted clause, a counterexample and confidence 0.9, so the evidence
bar passed them through. This is the concrete case for the next step already scheduled in
the plan: **execute** the counterexample and keep the drift claim only if the code really
behaves as alleged. A fabricated counterexample cannot survive being run.

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

specdrift build                       # materialise and validate all 86 cases
specdrift run --detector specguard    # also: keyword, wholefile
specdrift retrieval-eval              # Stage 1 Recall@1/3/5
specdrift score --detector all
specdrift report                      # results/report.html and results/report.md
```

The whole pipeline takes about 30 seconds from cold with the offline stand-in.

### The demo

```bash
./scripts/demo.sh
```

Deletes a validation check from `library`, leaves its comment in place, and shows the
keyword baseline calling it `COMPLIANT` while SpecGuard flags `R09` as `DRIFT`. Runs in
about two seconds and never modifies anything under `projects/`.

### The dashboard

```bash
cd web && npm install && npm run build && cd ..
specdrift serve            # http://127.0.0.1:8000
```

For UI development, run `specdrift serve` and `npm run dev` side by side; Vite proxies
`/api` to port 8000.

## Using a real model

The default provider is `fake`: a deterministic offline stand-in so the pipeline, the
demo and the dashboard all work with no API key. It compares the literal values and
named exceptions a rule states against the retrieved code, and knows nothing about
ordering or about behaviour no rule authorises. **It is not a model.** Every result
file records the model id, and `specdrift run` prints a warning when it is in use.

For model results, copy `.env.example` to `.env` and set:

```bash
LLM_PROVIDER=openai          # any OpenAI-compatible endpoint: Ollama, Groq, OpenRouter
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=                # leave empty for OpenAI itself
LLM_API_KEY=sk-...
```

Then `pip install -e ".[llm]"` and re-run. Responses are cached on the content of the
question, so only the chunks a case actually changed cost a call. The recorded specguard
run asked 1146 questions and made 252 calls, with 894 answered from a warm cache. A cold
cache costs all 1146, and repeat runs (`--run 2` and up) bypass the cache on purpose.

## How a case is built

`cases/*.yaml` holds one entry per case. The builder copies the host project to
`work/<case id>/` and applies a find/replace that **must** match exactly once, then the
validator compiles the file and runs the project's own test suite.

```yaml
- id: library-D1-02
  project: library
  category: D1            # D1..D9 drift, N1..N3 negative controls
  label: drift
  target_rules: [R06, R07]
  file: src/library/service.py
  find: '        if len(self.active_loans(member_id)) >= MAX_ACTIVE_LOANS:'
  replace: '        if len(self.active_loans(member_id)) > MAX_ACTIVE_LOANS:'
  gold_symbol: LibraryService.borrow
  note: "Allows a 4th active loan."
```

A patch may also be written as a list of lines. YAML block scalars strip the common
leading indentation, which would silently break an exact match against indented Python,
so a list of quoted lines is the way to write a multi-line patch:

```yaml
  find:
    - '        self.loans.append(loan)'
    - ''
    - '        self.audit.append(AuditEntry(...))'
```

A negative control that fails its own test suite is marked **invalid** and excluded: if
a "refactor" changes behaviour, it is not a refactor, and scoring it would corrupt the
false-alarm rate.

## The taxonomy

| ID | Category | Direction |
| --- | --- | --- |
| D1 | Boundary shift | forward |
| D2 | Value / constant drift | forward |
| D3 | Omitted check | forward |
| D4 | Weakened condition | forward |
| D5 | Sequence violation | forward |
| D6 | Error-handling drift | forward |
| D7 | Comment decoy | forward |
| D8 | Unauthorised scope creep | reverse |
| D9 | Output contract drift | forward |
| N1 | Unchanged code | control |
| N2 | Semantics-preserving refactor | control |
| N3 | Benign decoy | control |

## How scoring works

- A drift case is a **true positive** only when the detector flags the rule the
  injection targeted. A lucky flag on an unrelated rule earns nothing and is counted
  separately as a spurious flag.
- Some D8 cases name no rule, because no rule authorises the added behaviour. There a flag
  counts only if it was raised on the planted code (the detector retrieved the gold symbol,
  or cited its file); a flag raised elsewhere is spurious, like any other off-target flag.
  A detector that reports neither retrieval nor evidence gets the benefit of the doubt.
- A reverse-direction finding names no rule. On a D8 case it counts when it points at the
  planted code, whether or not the case also names a rule; on any other drift case it is a
  spurious flag.
- **Any** drift flag on a negative control is a false alarm, reverse findings included.
- `UNCERTAIN` counts as "not flagged". In Review 3 it becomes the abstention route.
- A miss is attributed to **retrieval** when the injected chunk was never shown, and to
  **reasoning** when it was shown and read wrongly. A detector with no retrieval stage
  is marked `n/a` rather than blamed for a stage it does not have.

## Design notes worth knowing

**The verifier never asks for a fix, and a drift claim must carry evidence.** Jin & Chen
(ASE 2026) found that asking a model to explain and propose a fix raised false rejection
sharply, and that most false rejections were unsupported "logic error" claims. So the
prompt forbids fix suggestions, and a `DRIFT` verdict without both a quoted clause and a
concrete counterexample is downgraded to `UNCERTAIN` before it is ever scored.

**Stage 1 resolves constants.** A rule like "the loan period MUST be 14 days" judged
against `day + LOAN_PERIOD_DAYS`, with the constant's definition out of view, produces a
detector that is not wrong so much as under-informed. When a retrieved chunk references
a module-level constant, the module chunk that defines it is added to the excerpt.
Adding this cut the false-alarm rate on the offline stand-in from 0.67 to 0.33.

**The keyword baseline reads comments on purpose.** Searching all source text including
comments is what makes it fooled by a comment decoy, which is the point of having it.
One side effect is worth knowing when reading its numbers: a rule-id annotation such as
`# R12` tokenises to the value `12`, so a rule stating `12` can look satisfied by its own
cross-reference.

## Layout

```
specdrift/
  spec/parser.py            spec.md -> numbered rules
  code/chunker.py           source -> function/method/class/module chunks
  bench/                    builder, validator, schema, build pipeline
  retrieval/                embedder (local or sentence-transformers), retriever, Recall@k
  verify/                   llm adapter, prompt, verifier, SpecGuard engine, reverse check
  baselines/                keyword, wholefile
  eval/                     metrics, report + templates
  api/                      FastAPI app, in-memory store, response models
  cache.py cli.py config.py live.py registry.py runner.py
projects/                   library, wallet, ratelimiter  (spec.md + src/ + tests/)
cases/                      one YAML manifest per project, plus built.jsonl
web/                        Vite + React + Tailwind dashboard
results/ cache/ work/       generated, git-ignored
tests/                      the framework's own tests (162, none call a model)
```

## Commands

| Command | What it does |
| --- | --- |
| `specdrift build [--project P] [--case ID]` | Materialise and validate cases. A filtered build updates only those rows. |
| `specdrift run --detector X [--project P] [--limit N] [--run K] [--repeat N]` | Write `results/X/verdicts.jsonl` (later runs: `verdicts.runK.jsonl`). `--run K` for K>1 bypasses the cache; `--repeat N` makes N consecutive runs. |
| `specdrift score --detector X\|all` | Write `metrics.json` and `per_category.csv`. |
| `specdrift stability --detector X` | Mean, run-to-run spread and bootstrap 95% CIs over every stored run. |
| `specdrift oracles` | Check each escaping drift case against its oracle test. |
| `specdrift report` | Render `results/report.html` and `report.md`. |
| `specdrift retrieval-eval` | Stage 1 Recall@1/3/5 against the gold chunk. |
| `specdrift check <dir> [--diff-from REF]` | Live check of a working directory. Exits 1 on drift. |
| `specdrift serve [--port N]` | API, plus the built dashboard when `web/dist` exists. |

## Tests

```bash
pytest                      # the framework: 162 tests
pytest projects/library     # a host project's own suite
```

No test in `tests/` ever calls a model; the fake is scripted with canned JSON. CI
(`.github/workflows/ci.yml`) runs `ruff check`, `mypy`, `pytest` and the web typecheck/build.

## Running the API safely

`specdrift serve` binds to `127.0.0.1`. The routes that spend LLM money or store uploads
(`/api/check`, `/api/sweep`, `/api/uploads*`, `/api/reload`) are guarded by settings in `.env`:

| Setting | Default | Effect |
| --- | --- | --- |
| `API_TOKEN` | empty (open) | When set, those routes need `Authorization: Bearer <token>` or `X-API-Token`. |
| `API_RATE_LIMIT_PER_MIN` | 30 | Per-client limit on those routes; 0 turns it off. |
| `UPLOAD_TTL_HOURS` | 24 | Stored uploads older than this are deleted on the next upload. |
| `DEMO_PACING` | true | Paces the live-check stream so cached answers are watchable; set false for scripts. |

Archive uploads are capped while streaming (1.5 MB). **Uploaded code and specs are sent to
the configured LLM provider when checked**; upload responses carry an `X-Data-Notice`
header saying so.

## Reproducing the numbers

`results/` is git-ignored because it is regenerated, so the numbers above are frozen in
`results-snapshot/`: metrics, stability intervals, oracle verdicts and every verdict file
(annotated and rule-id-stripped). Re-score without a model key by copying a detector's
`verdicts.jsonl` into `results/<detector>/` and running `specdrift score`. Runs made before
the embedder was recorded in `run.json` used the local hashing embedder.

## Not built yet

Deferred by design, each with a slot in the code: the adversarial second pass
(`verify/adversary`), the Semcheck baseline,
calibration and an abstention threshold, a per-rule whole-file baseline (to separate
retrieval from prompt shape), and seven more host projects.
