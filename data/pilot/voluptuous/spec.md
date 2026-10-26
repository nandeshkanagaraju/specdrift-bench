# voluptuous specification

## Range limits

- **R01** `Range.__call__` MUST accept a value equal to `min` when `min_included` is true.
- **R02** `Range.__call__` MUST reject a value equal to `min` when `min_included` is false.
- **R03** `Range.__call__` MUST accept a value equal to `max` when `max_included` is true.
- **R04** `Range.__call__` MUST reject a value equal to `max` when `max_included` is false.
- **R05** `Range.__call__` MUST raise `RangeInvalid` for a value that has no ordering against the limits.

## Clamping

- **R06** `Clamp.__call__` MUST return `min` for a value below `min`.
- **R07** `Clamp.__call__` MUST return `max` for a value above `max`.

## Length

- **R08** `Length.__call__` MUST raise `LengthInvalid` for a value shorter than `min`.
- **R09** `Length.__call__` MUST raise `LengthInvalid` for a value longer than `max`.

## Booleans

- **R10** `Boolean` MUST return `True` for the strings `1`, `true`, `yes`, `on` and `enable`, ignoring case.
- **R11** `Boolean` MUST return `False` for the strings `0`, `false`, `no`, `off` and `disable`, ignoring case.
- **R12** `Boolean` MUST raise `BooleanInvalid` for a string that is not one of those words.

## Truthiness

- **R13** `IsFalse` MUST raise `FalseInvalid` for a value that is true in the Python sense.

## Combinators

- **R14** `Any._exec` MUST return the result of the first sub-validator that accepts the value.
- **R15** `All._exec` MUST pass the output of each sub-validator to the next one.

## Matching

- **R16** `Match.__call__` MUST raise `MatchInvalid` for a value that is not a string.
- **R17** `Match.__call__` MUST match the pattern at the start of the string only.

## Email

- **R18** `Email` MUST reject a string that contains no `@`.
