# Rule extraction and oracle prompts (Stage B, draft v0)

Status: draft. Nothing here has been run against a model. Prompts are versioned; bump `RULE_PROMPT_VERSION`
and `ORACLE_PROMPT_VERSION` on any wording change and regenerate that repo's files.

## 1. What this produces, and why it is split this way

For each accepted repo the assembler (`specdrift data-assemble`) needs three things in the project folder:

| File | Made by | Checked by |
| --- | --- | --- |
| `spec.md` | code, rendered from the LLM's JSON (section 3) | the existing parser, the lint in section 4 |
| `rules.yaml` (rule -> symbols, oracle path) | code, from the same JSON | the existing `load_rule_map` |
| `oracles/test_rNN.py`, one per rule | LLM, prompt B (section 5) | must pass on the unmodified repo, section 6 |

**The model never writes `spec.md` or `rules.yaml` itself.** It returns JSON and a script renders both files.
That removes a whole class of format failures, and it lets every claim be machine-checked: each rule must name symbols
that the chunker can resolve and quote a line of code that is really in the file.

Two calls per repo for rules (A, one call) and one call per rule for oracles (B). Both at temperature 0, cached on the
content of the request, with the model id recorded in `provenance.gen_model` of every example built from them.

Use a model that is **not** the one being compared against `specguard` on the synthetic validation split. Otherwise
the same model's habits shape both the rules and the judgement of them.

## 2. Inputs the script supplies

- the repo README (first 6,000 characters), if any
- every source file, as `=== path ===` followed by numbered lines, from `scripts/shortlist_repos.py`'s source-file selection
- the list of resolvable symbols, produced by `chunk_workspace` (`func`, `Class`, `Class.method`, `<module>`),
  so the model picks from real names instead of inventing them
- the repo's own test file names only (not their contents), as a hint to what behaviour the authors consider important

Tests are withheld on purpose: rules derived from tests describe the tests, and the project's own suite is the thing
the oracles are meant to improve on.

## 3. Prompt A: extract rules (one call per repo)

`RULE_PROMPT_VERSION = "v0"`

**System**

```
You write a specification for an existing Python library, as a list of short, testable rules. A reader will
later decide, for each rule, whether a changed version of the code still obeys it, so every rule must be
something a test could check by running the code.

Write a rule only when the code or the README states or clearly implies it. Do not invent behaviour. Do not
describe how the code is organised, how fast it is, how it logs, or how it is formatted.

A good rule:
- has exactly one requirement, using MUST or MUST NOT once;
- states a concrete value, a named exception, a boundary (at least, more than, exactly), an ordering
  (before, only after), or a returned shape, so a one-character change to the code would break it;
- names the public function or class it is about in backticks;
- is one sentence, at most 40 words.

A bad rule is vague ("handles errors properly"), a restatement of a function name ("`parse` parses input"),
a list of several requirements joined by "and", or about internals no caller can observe.

Prefer rules about: limits and thresholds, defaults, error conditions and the exception raised, argument
validation, ordering of steps, what is returned for empty or edge input, and units or rounding.

Return JSON only, matching the schema. Write between 8 and 20 rules. If the library has fewer than 8 such
behaviours, write fewer; never pad.
```

**User**

```
LIBRARY: {repo_name}

README:
{readme}

SOURCE FILES (with line numbers):
{numbered_sources}

RESOLVABLE SYMBOLS (use only these in "symbols"):
{symbol_list}

Return:
{
  "rules": [
    {
      "text": "<one sentence, one MUST or MUST NOT>",
      "section": "<2-4 word topic heading>",
      "symbols": ["<symbol from the list>", ...],
      "grounding": "documented" | "code",
      "evidence": {"file": "<path>", "quote": "<one line copied exactly from that file>"}
    }
  ]
}
```

`grounding` is `documented` when the README or a docstring states the behaviour, `code` when it is read off the code only.
A rule that is `code` only, and quotes a line that is just a constant or condition, is allowed; the quote is what lets
the script check it was not invented.

**Rendering** (deterministic, in code, not in the model): ids `R01`..`Rnn` in the order returned; sections become
`##` headings; each rule becomes `- **Rnn** {text}`; `rules.yaml` gets `Rnn: {symbols: [...], oracle: [oracles/test_rnn.py]}`.

## 4. Lint on the extracted rules (deterministic, no model)

A rule is dropped, and the reason logged, if any of these fail (except the warning). Fewer than 6 surviving rules rejects the repo.

| Check | Rule |
| --- | --- |
| Shape | one sentence, at most 40 words, exactly one `MUST` or `MUST NOT` |
| Anchor (warning only) | contains a number, a backticked identifier, a quoted string, or an ordering word (`before`, `after`, `only`, `first`, `then`). A rule without one is kept and flagged: "A new bucket MUST start full" has none and is a good rule. The kill-rate gate in section 6 is what decides whether a rule is checkable. |
| Hedges | none of: should, may, might, usually, typically, generally, appropriate, properly, correctly, reasonable, efficient, gracefully, as expected |
| Compound | no `, and ` or ` and MUST` joining two requirements (my toy project's R01 would fail this and should be split) |
| Grounded | `evidence.quote` occurs verbatim in `evidence.file` (whitespace-normalised) |
| Resolvable | every symbol is in the symbol list, and the quoted line lies inside a chunk of one of them |
| Not a test | the rule does not mention tests, fixtures or mocks |
| Distinct | no two rules cite the same symbols and the same line of code, and none is within 3% edit distance of another. Measured in the pilot: edit distance cannot tell a paraphrase from an opposite rule ("accept a value equal to `min`" vs "reject a value equal to `min`" are 0.09 apart, `min` vs `max` three characters), so a similarity threshold either drops real rules or keeps duplicates. |
| Not the benchmark | not within 20% of any frozen test rule (reuses the leakage check) |

Dry run of this lint on the 40 hand-written rules of the three host projects: 36 pass. The four misses are two compound rules (`MUST NOT borrow, and ... MUST raise`, which should be split, so the lint is right) and two rules with no anchor (which is why the anchor check is only a warning). The toy project's R01 and R04 are also compound.

## 5. Prompt B: write one oracle (one call per surviving rule)

`ORACLE_PROMPT_VERSION = "v0.1"` (v0 allowed only a single call per test; stateful libraries such as cachetools need set-up lines)

The oracle is the judge of every DRIFT label built from this rule, so it is the part most worth being strict about.
It is written to be read by `parse_failure` in `specdrift/data/assemble.py`, which understands exactly two assertion shapes.

**System**

```
You write a pytest file that decides whether a Python library still obeys ONE specification rule.
The file will be run against the original code, where it must pass, and against slightly changed copies of the
code, where it must fail if the change breaks the rule. A one-character change (a comparison operator, a constant,
a deleted check, a different exception) must make it fail.

Requirements:
- Test only what the rule says. Do not assert anything the rule does not state, even if the code does it.
- For every number or boundary in the rule, test the value exactly at the boundary and one step on each side.
- Use only the public names in the symbol list, imported exactly as shown.
- A test may first set things up with plain assignments and single calls, then check with exactly two shapes:
    assert <expression> == <literal>          (or `is True`, `is False`, `is None`)
    with pytest.raises(<ExceptionName>):
        <one call expression>
  The expected value must be written out as a literal; never compute it by calling the code under test.
- No loops, conditionals, helper functions, classes, lambdas, comprehensions, try blocks or imports inside a test.
- Each test function checks one thing and has a name that says what.
- No network, files, clock, randomness, sleeping, mocks, fixtures or parametrize.
- At most 40 lines, imports included. No comments.

Return only the Python source of the file.
```

**User**

```
RULE {id}: {text}

IMPORT AS:
{import_lines}

CODE THE RULE IS ABOUT:
{symbol_sources}

Write the pytest file.
```

`import_lines` is computed by the script from the repo layout (`from semver import VersionInfo`), not guessed by the model.

## 6. Gates an oracle must pass before it is used (deterministic)

1. **Passes on the unmodified repo**, run in the sandbox 3 times. (This is already enforced: the assembler excludes any rule whose oracle fails on the original.)
2. **Only the two allowed assertion shapes**, checked by parsing the file with `ast`; anything else is rejected, because the counterexample reader cannot interpret it.
3. **Sensitive to its own rule.** Originally "fails on at least one injected mutant". The pilot showed that is the wrong test: of 6 oracles that killed nothing, I hand-mutated 4 on exactly the behaviour their rule describes and all 4 failed. The rest killed nothing because the injector had no operator for the rule's mechanism, or because the mutation (`[:3]` to `[:4]` in a version compare) does not violate a rule about the *build* part. So "killed nothing" is reported, not enforced. What is enforced: a person reads the oracle (section 7), and for a sample the
   rule's cited line is mutated by hand and the oracle must fail.
4. **No import of anything outside the standard library and the repo.**
5. **No tautology.** The oracle must not call the function under test to compute its own expected value (checked by looking for the called name on the right-hand side of `==`).

## 7. Human spot-check (before any scale-up)

Pilot on 3 repos first (section 9). A person reads a random 10 percent of rules (at least 15) and 10 percent of oracles and answers, per item:

| Question | Pass if |
| --- | --- |
| Is the rule true of the library? | yes, per the README or by reading the code |
| Is it about observable behaviour, not an accident of the implementation? | yes |
| Is it one requirement a test could decide? | yes |
| Does the oracle test the rule and nothing else? | yes |
| Does the oracle encode a bug (it passes only because the code is wrong)? | no |

Proceed only if at least 90 percent of rules and 85 percent of oracles pass. Otherwise change the prompt, bump the version, and
re-run the pilot. Prompts are frozen once the pilot passes, and the frozen version is what the paper cites.

## 8. Cost, in tokens (prices are not guessed here)

For a repo of about 2,000 source lines:

| Call | Input | Output | Calls per repo |
| --- | ---: | ---: | ---: |
| A: rules | 20,000 to 30,000 | 1,500 | 1 |
| B: oracle | 1,500 to 3,000 | 300 | 10 to 15 |

About 50,000 to 75,000 input and about 6,000 output tokens per repo, so about 1.5 to 2.2 million input and 0.2 million output for
30 repos, before retries. Multiply by your chosen model's published per-token rates. The response cache means a re-run costs nothing
unless the wording changed.

## 9. Pilot, in order

1. A person runs `scripts/shortlist_repos.py --verify` on the shortlist (executes third-party tests in the sandbox; see `data/repos.csv`).
2. Pick 3 verified repos, one each of: validation (`validators`), version logic (`python-semver`), stateful behaviour (`cachetools`).
3. Run prompt A and the section 4 lint. Read every rule for the first repo, the 10 percent sample for the others.
4. Run prompt B for each surviving rule, apply the section 6 gates, report the kill rates.
5. Run `data-inject` and `data-assemble` on each; run `data-check` against the frozen test set.
6. Decide on the section 7 thresholds, freeze the prompts, then scale to the rest of the shortlist.

## 10. Known risks

| Risk | Mitigation |
| --- | --- |
| The model states behaviour the code does not have | `evidence.quote` must exist in the file; the oracle must pass on the original |
| The oracle encodes an existing bug as the spec | the section 7 question; rules marked `documented` are trusted more than `code` ones, and the label is recorded |
| A weak oracle makes real drift look compliant | the kill-rate gate; wrong-rule examples record `violates_other_rules` |
| Popular libraries are in the training data of the model being fine-tuned | prefer repos with fewer stars for the training split; report the star count of each repo in the paper as a threat |
| Rule wording from one LLM leaks its style into the data | one generator model, recorded; a second model rewords 10 percent as a robustness check |
| The generator and a compared detector are the same model | choose a generator that is not the baseline detector |

## 11. Pilot results (measured, 24 Oct 2026)

Generator: **Claude, interactively**, following prompts A and B as written (no API run, no cost). Treat lint-drop rates as indicative: a different model, or the same model through the API, may differ.
Repos: `python-semver` (20 rules), `cachetools` (19), `voluptuous` (18). Verification of the 30 shortlisted repos: 11 passed the sandboxed 3-of-3 run;
the 19 that failed all needed test-only dependencies (`hypothesis`, `freezegun`, `tornado`, `pexpect`, `ruamel`, `whatever`), a generated `_version` file, stdin, or the home directory.

| What | Result |
| --- | --- |
| Rules after lint | 57 of 57 kept, after 3 lint defects were fixed (below) |
| Oracles | 57 of 57 pass the static gate and pass together on the unmodified library |
| Examples, random mutants | 207 (59 DRIFT, 88 COMPLIANT, 60 UNCERTAIN); `data-check` against the frozen test set: clean |
| Examples, targeted mutants | 64 mutants instead of 248 gave 51 DRIFT instead of 59 |
| Rules with at least one DRIFT example | 29 of 57 (random), 24 of 57 (targeted), **33 of 57 together (58%)** |
| UNCERTAIN share | 29% (semver 43%, cachetools 22%, voluptuous 15%); the target was 10% |
| Mutants the project's own tests miss, rescued by an oracle | voluptuous 8; semver and cachetools 0 |

**Defects the pilot found and that are now fixed** (each has a test that fails without the fix):

1. The "is about tests" check dropped a good rule because it contained the word "test" ("an equality test"). It now matches the test suite, not the word.
2. The duplicate check by edit distance is wrong at every threshold. At 0.20 it dropped "size is negative" as a duplicate of "size is larger than `maxsize`"; at 0.10 it dropped "accept a value equal to `min`" as a duplicate of "reject a value equal to `min`" (0.09 apart; `min` vs `max` is three characters). Duplicates are now rules that cite the same symbols and the same line, or are within 3% of each other's text.
3. The counterexample reader mishandled `AssertionError: assert 'a' == 'b'` (pytest's form when it adds a diff) and an exception raised while evaluating an assert's left side.
4. The validator rejected a class chunk whose trailing blank line the chunker trims; only the module chunk has gaps that shift numbering.
5. `data-assemble` crashed with a traceback on a missing mutants file.
6. The kill-rate gate gave false alarms (section 6, gate 3).

**What the pilot does not fix, and the next work it points at**

- **The injector was the bottleneck, not the sampling.** 22 of 57 rules cited a line that none of its operators could change (`if not rc1:`, `return func(v)`, `self.__touch(key)`, `prefix = "=="`, a format string). Nine operators were added in response (section 12).
- **Retrieval, not labelling, drives the UNCERTAIN share.** The local hashing embedder misses the right method of a class with many methods (semver's `Version`). Either keep this (it is what production shows the model) and cap UNCERTAIN in the final mix, or raise `--gold-view`. This is also a finding about Stage 1 for the thesis.
- **A rule whose symbol is a class** (semver's R05 cites `Version`, the class header holding the regular expression) makes every method of the class a candidate for its oracle: 82 oracle runs for one rule. Correct but wasteful; a `Class#header` symbol would fix it.
- **Voluptuous' own suite looks weaker than it is** because `-o addopts=` also drops its `--doctest-glob`; "survived" means "survived the pytest suite without its doctests".
- **The human spot-check has not been done.** `docs/pilot-spot-check.md` is the sheet. Until it passes, none of this is ready to scale.

## 12. After adding the missing operators (measured, same three repos, same oracles)

New operators: `drop_not`, `flip_is`, `flip_in` (D4), `invert_condition` (D4), `string` and `arith` (D2), `drop_statement` and `pass_statement` (D3), `return_none_expr` (D9), `swap_args` (D5).
Each has tests for the cases it must leave alone (unary minus, `for x in`, docstrings, f-strings, the only statement in a block, non-ASCII lines, `isinstance` arguments), and each guard was disabled in turn to confirm a test fails.

| Step | Cited lines an operator can change | Rules with a DRIFT example | DRIFT examples | Mutants run |
| --- | ---: | ---: | ---: | ---: |
| Random sample, original 7 operators | 35 / 57 | 29 / 57 | 59 | 248 |
| Targeted at the cited lines, original 7 | 35 / 57 | 24 / 57 | 51 | 64 |
| Targeted, + new operators | **54 / 57** | 36 / 57 | 142 | 159 |
| Targeted, + new operators, + recovery of retrieval misses | 54 / 57 | **43 / 57 (75%)** | **173** | 159 |

Also added: when Stage 1 retrieval misses the changed code of a rule that *was* violated, the assembler now emits **two** examples: the realistic view labelled UNCERTAIN, and a second view that shows the changed code labelled DRIFT
(`--gold-on-miss`, on by default). Before this, those violations produced only an UNCERTAIN example, so the model never saw the DRIFT that goes with the code. The 369 examples (173 DRIFT, 111 COMPLIANT, 85 UNCERTAIN) pass the validator and the frozen-test-set check.

What still has no DRIFT example (14 rules): 8 where the oracle ran on mutants and none broke its rule (the mutation does not violate that rule, or the oracle is too weak, which only the human spot-check can separate), and 6 where every mutant on the cited line crashed
(for example `key = next(...)` replaced by `pass` leaves `key` undefined). Crashes are excluded on purpose: they show the code no longer loads, not that a rule is broken. Three cited lines remain out of reach of any line-level operator: a regular expression, an error-message string and a decorator.

Caveats for whoever builds the final mix: voluptuous supplies 95 of the 173 DRIFT examples (35 of them mutants its own suite missed), so cap examples per rule and per repo; and 85 of 369 are UNCERTAIN (23%), still above the 10% target, mostly from retrieval misses in semver.

## 13. Adding N2 and N3 (measured, same three repos)

Generated and verified: 327 behaviour-preserving examples (142 N2, 185 N3) from 4 hand-built refactor families and 3 decoy families, in two passes per repo (targeted at the cited lines, and sampled).
Every candidate had to pass the project's suite *and* every covered rule's oracle.

| Mix (same settings, held-out project `cachetools`) | Train | Val | Stage B limited by | N1 / N2 / N3 in train |
| --- | ---: | ---: | --- | --- |
| Before: drift and unchanged code only | 121 | 81 | COMPLIANT | 13 / 0 / 0 |
| After: + N2/N3 | **414** | 162 | **DRIFT** | 21 / 45 / 50 |
| After, benchmark-overlapping families held out | 360 | 127 | COMPLIANT | 25 / 32 / 38 |
| After, no Stage A | 277 | 108 | DRIFT | 21 / 44 / 51 |

The bottleneck moved from COMPLIANT to DRIFT, and the training set is 3.4 times larger at the same label shares (35 / 55 / 10).

**Defects the real run found, now fixed with tests** (a toy project could not have shown the first):

1. `decoy_dead_branch` inserted `if False: pass` before an `elif`, re-attaching it to the new `if` and changing behaviour. The suite caught it, but the assembler then labelled three such mutants **DRIFT/N3**.
   The generator no longer inserts before `elif`/`else`; the sample used for the behaviour-preservation test now contains an `elif` chain, so that test catches the bug independently; and the assembler never turns a non-preserved N2/N3 mutant into any example.
2. `ast.Le` and `ast.Ge` do not exist (`LtE`, `GtE`); `swap_compare_sides` would have crashed on first use. mypy found it.
3. A refactor the retriever did not show produced no example (137 skipped in semver alone); it now produces a second example with a view that shows it.
4. Every assembler run repeats the unchanged-code (N1) examples with the same ids, so combining runs collided; identical examples are now merged and only an id with *different* content is an error.
5. The "oracles that failed on no mutant" warning fired on benign runs, where that is the correct outcome; benign mutants are no longer counted.

**What this does not establish.** N2/N3 verification rests on the oracles: a refactor that changes behaviour no oracle checks would be accepted. The spot-check (`docs/pilot-spot-check.md`) is still not done. And the benchmark's N2/N3 cases belong to the same
families as `rename_local`, `extract_temp`, `decoy_comment` and `decoy_docstring`; the held-out-family mix is how to measure whether results depend on that.
