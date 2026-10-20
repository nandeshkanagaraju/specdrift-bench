# Changelog

## Unreleased

### Reverse direction
- `verify/reverse.py`: a code-to-rules pass that audits every function and method against the
  whole rule list for behaviour no rule describes (D8 scope creep). Findings must quote the
  code verbatim, and functions already reported on the pristine project are accepted.
- Detectors `reverse` and `specguard-reverse` (both directions); verdicts carry a `direction`.
- Scoring: a reverse finding on the planted code catches a D8 case; elsewhere it is spurious
  or, on a control, a false alarm. D8 recall 0.17 -> 0.78 over three runs.

### Measurement
- `strict_precision`: flags on non-target rules of drift cases now count as false positives.
- D8 scoring: on rule-less scope-creep cases a flag counts only if raised on the planted code.
- `specdrift run --repeat N` stores each run beside run 1; `specdrift stability` reports means,
  run-to-run spread and bootstrap 95% intervals.
- Oracle tests (`cases/oracles/`, `specdrift oracles`) confirm 12 of the 13 drift cases that
  escape the project's tests; `library-D9-02` is waived as not behaviourally observable.
- Rule-id ablation (`STRIP_RULE_IDS=true`): LLM detectors are unaffected, keyword is not.
- Run stats record the embedder and whether rule ids were stripped.
- `results-snapshot/`: committed results so the README numbers can be re-scored without a key.

### Fixes
- A model answering a line range such as `"41-44"` no longer crashes a run.
- `.env` is resolved from the repository root, not the current directory.
- The Anthropic adapter no longer sends `temperature`, which the current SDK rejects.
- Unknown `/api/...` paths return 404 instead of the web app's index page.

### API
- Optional `API_TOKEN`, a per-client rate limit, a streaming upload cap, upload expiry,
  a data-handling notice header, and `DEMO_PACING` for the live-check stream delays.

### Engineering
- One shared `excerpt_for` replaces three copies of the rank/context loop.
- Tests for the CLI, LLM adapters, report, sweep and SPA fallback; ruff, mypy and CI added.
