# SpecDrift-Bench results

_Generated 2026-10-20. Preliminary, one run per detector._

## Dataset

86 valid cases across library, ratelimiter, wallet &mdash;
59 drift, 27 negative controls.
**22% of drift cases still pass the host project's own test suite.**

| Cat | Category | n | Passes tests |
| --- | --- | ---: | ---: |
| D1 | Boundary shift | 8 | 1/8 (12%) |
| D2 | Value / constant drift | 9 | 1/9 (11%) |
| D3 | Omitted check | 6 | 0/6 (0%) |
| D4 | Weakened condition | 6 | 0/6 (0%) |
| D5 | Sequence violation | 6 | 2/6 (33%) |
| D6 | Error-handling drift | 6 | 0/6 (0%) |
| D7 | Comment decoy | 6 | 0/6 (0%) |
| D8 | Unauthorised scope creep | 6 | 6/6 (100%) |
| D9 | Output contract drift | 6 | 3/6 (50%) |
| N1 | Unchanged code | 3 | 3/3 (100%) |
| N2 | Semantics-preserving refactor | 18 | 18/18 (100%) |
| N3 | Benign decoy | 6 | 6/6 (100%) |

## Detector comparison

| Detector | Model | Precision | Recall | F1 | False-alarm rate | Uncertain | LLM calls |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| specguard | gpt-4o-mini | 0.65 | 0.54 | 0.59 | 0.63 | 0.06 | 252 |
| keyword | n/a | 0.33 | 0.08 | 0.14 | 0.37 | 0.00 | 0 |
| wholefile | gpt-4o-mini | 0.91 | 0.17 | 0.29 | 0.04 | 0.01 | 86 |

## Per category

D rows are recall, N rows are the false-alarm rate on controls.

| Cat | Category | n | specguard | keyword | wholefile |
| --- | --- | ---: | ---: | ---: | ---: |
| D1 | Boundary shift | 8 | 25% | 12% | 38% |
| D2 | Value / constant drift | 9 | 100% | 22% | 44% |
| D3 | Omitted check | 6 | 33% | 17% | 0% |
| D4 | Weakened condition | 6 | 100% | 0% | 17% |
| D5 | Sequence violation | 6 | 33% | 0% | 0% |
| D6 | Error-handling drift | 6 | 33% | 0% | 0% |
| D7 | Comment decoy | 6 | 67% | 0% | 17% |
| D8 | Unauthorised scope creep | 6 | 17% | 17% | 0% |
| D9 | Output contract drift | 6 | 67% | 0% | 17% |
| N1 | Unchanged code | 3 | 67% | 33% | 0% |
| N2 | Semantics-preserving refactor | 18 | 67% | 33% | 0% |
| N3 | Benign decoy | 6 | 50% | 50% | 17% |

## Stage 1 retrieval (local-hashing-2048)

| Cat | n | R@1 | R@3 | R@5 |
| --- | ---: | ---: | ---: | ---: |
| D1 | 12 | 25% | 83% | 100% |
| D2 | 9 | 0% | 67% | 89% |
| D3 | 8 | 0% | 50% | 75% |
| D4 | 8 | 0% | 100% | 100% |
| D5 | 6 | 83% | 100% | 100% |
| D6 | 6 | 0% | 67% | 100% |
| D7 | 6 | 50% | 83% | 100% |
| D8 | 3 | 0% | 33% | 33% |
| D9 | 6 | 100% | 100% | 100% |
| **all** | 64 | 27% | 78% | 92% |

## Why drift was missed

| Detector | Retrieval | Reasoning | n/a |
| --- | ---: | ---: | ---: |
| specguard | 11 | 16 | 0 |
| keyword | 0 | 0 | 54 |
| wholefile | 0 | 0 | 49 |

## Example verdicts

### specguard &mdash; caught drift (`library-D2-01`, D2)

Loan period silently becomes 3 weeks.

- Rule `R12` &rarr; **DRIFT** (confidence 1.00)
- Clause: _The loan period MUST be 14 days from the borrow date._
- Counterexample: given day = 1, expected due_on = 15, actual due_on = 22

### specguard &mdash; missed drift (`library-D1-01`, D1)

Turns away a member who is exactly 18, which R01 allows.

- Rule `R01` &rarr; **UNCERTAIN** (confidence 0.50)
- Missed via: retrieval

### specguard &mdash; false alarm on a negative control (`ratelimiter-N1-01`, N1)

The project exactly as written. Must not be flagged.

- Rule `R02` &rarr; **DRIFT** (confidence 0.90)
- Clause: _A new bucket MUST start full._
- Counterexample: given bucket_for('client_1', now=0), expected tokens = 10.0, actual tokens = 0.0

### keyword &mdash; caught drift (`library-D1-01`, D1)

Turns away a member who is exactly 18, which R01 allows.

- Rule `R01` &rarr; **DRIFT** (confidence 0.60)
- Clause: _A member MUST be at least 18 years old at registration._
- Counterexample: given the rule's own vocabulary, expected every term and number of the rule appears in the code, actual only 40% of the rule's terms appear in the code

### keyword &mdash; missed drift (`library-D1-02`, D1)

Allows a 4th active loan.

- Rule `R01` &rarr; **DRIFT** (confidence 0.60)
- Missed via: n/a
- Clause: _A member MUST be at least 18 years old at registration._
- Counterexample: given the rule's own vocabulary, expected every term and number of the rule appears in the code, actual only 40% of the rule's terms appear in the code

### keyword &mdash; false alarm on a negative control (`library-N1-01`, N1)

The project exactly as written. Must not be flagged.

- Rule `R01` &rarr; **DRIFT** (confidence 0.60)
- Clause: _A member MUST be at least 18 years old at registration._
- Counterexample: given the rule's own vocabulary, expected every term and number of the rule appears in the code, actual only 40% of the rule's terms appear in the code

### wholefile &mdash; caught drift (`library-D1-01`, D1)

Turns away a member who is exactly 18, which R01 allows.

- Rule `R01` &rarr; **DRIFT** (confidence 0.90)
- Clause: _A member MUST be at least 18 years old at registration._
- Counterexample: given age = 17, expected UnderageMember exception, actual No exception raised

### wholefile &mdash; missed drift (`library-D1-02`, D1)

Allows a 4th active loan.

- Rule `R06` &rarr; **COMPLIANT** (confidence 1.00)
- Missed via: n/a

### wholefile &mdash; false alarm on a negative control (`wallet-N3-02`, N3)

Docstring claims the cap is gone; the code still applies it.

- Rule `R11` &rarr; **DRIFT** (confidence 0.90)
- Clause: _the transfer fee MUST be 1% of the amount, with a minimum of 0.10 and a maximum of 5.00_
- Counterexample: given transfer_fee(Decimal('500.00')), expected 5.00, actual 5.00

