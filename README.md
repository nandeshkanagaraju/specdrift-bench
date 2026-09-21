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
| Detectors | `specguard` (retrieval + verification), `keyword` (vocabulary matching), `wholefile` (one prompt, whole codebase) |
| Outputs | Per-category recall and false-alarm rate, Recall@k, retrieval-vs-reasoning attribution, an HTML report, and a web dashboard |

Every drift case records `escapes_tests`: whether the host project's own test suite
still passes after the injection. On this dataset **22% of drift survives the tests**,
and unauthorised scope creep (D8) survives 100% of the time — the tests were written
before the behaviour existed, so they cannot fail on it.

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
question, so only the chunks a case actually changed cost a call: a full 86-case run is
414 calls, not 1146.

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
- D8 cases name no rule, because no rule authorises the added behaviour; any drift flag
  on the case counts.
- **Any** drift flag on a negative control is a false alarm.
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
  verify/                   llm adapter, prompt, verifier, SpecGuard engine
  baselines/                keyword, wholefile
  eval/                     metrics, report + templates
  api/                      FastAPI app, in-memory store, response models
  cache.py cli.py config.py live.py registry.py runner.py
projects/                   library, wallet, ratelimiter  (spec.md + src/ + tests/)
cases/                      one YAML manifest per project, plus built.jsonl
web/                        Vite + React + Tailwind dashboard
results/ cache/ work/       generated, git-ignored
tests/                      the framework's own tests (104, none call a model)
```

## Commands

| Command | What it does |
| --- | --- |
| `specdrift build [--project P] [--case ID]` | Materialise and validate cases. A filtered build updates only those rows. |
| `specdrift run --detector X [--project P] [--limit N] [--run K]` | Write `results/X/verdicts.jsonl`. `--run K` for K>1 bypasses the cache. |
| `specdrift score --detector X\|all` | Write `metrics.json` and `per_category.csv`. |
| `specdrift report` | Render `results/report.html` and `report.md`. |
| `specdrift retrieval-eval` | Stage 1 Recall@1/3/5 against the gold chunk. |
| `specdrift check <dir> [--diff-from REF]` | Live check of a working directory. Exits 1 on drift. |
| `specdrift serve [--port N]` | API, plus the built dashboard when `web/dist` exists. |

## Tests

```bash
pytest                      # the framework: 104 tests
pytest projects/library     # a host project's own suite
```

No test in `tests/` ever calls a model; the fake is scripted with canned JSON.

## Not built yet

Deferred by design, each with a slot in the code: the adversarial second pass
(`verify/adversary`), the reverse-direction authorisation pass, the Semcheck baseline,
repeated runs with variance, calibration and an abstention threshold, and seven more
host projects.
