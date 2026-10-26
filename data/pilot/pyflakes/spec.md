# pyflakes specification

## API

- **R01** `check` MUST return the number of warnings it found in the source.
- **R02** `check` MUST report a syntax error to the reporter and return 1 for source that does not parse.
- **R03** `isPythonFile` MUST return `False` for a filename that ends with `~`.
- **R04** `iterSourceCode` MUST yield a path that is not a directory unchanged.

## Reporter

- **R05** `Reporter.flake` MUST write the message to the warning stream followed by a newline.
- **R06** `Reporter.unexpectedError` MUST write the filename and the message, separated by a colon, to the error stream.
- **R07** `Reporter.syntaxError` MUST write the filename, line number, column and message to the error stream, leaving out the column when the offset is `None`.

## Control flow

- **R08** `Checker` MUST report a `return` statement that is outside a function.
- **R09** `Checker` MUST report a `yield` expression that is outside a function.
- **R10** `Checker` MUST report a `continue` statement that is not inside a loop.
- **R11** `Checker` MUST report a `break` statement that is not inside a loop.

## Statement checks

- **R12** `Checker` MUST report an `assert` whose test is a non-empty tuple.
- **R13** `Checker` MUST report an `if` whose test is a non-empty tuple.
- **R14** `Checker` MUST report `raise NotImplemented`.
- **R15** `Checker` MUST report an f-string that has no placeholders.
- **R16** `Checker` MUST report an `is` or `is not` comparison against a constant that is not a singleton.
- **R17** `Checker` MUST report each occurrence of a dict key that is repeated with different values.
- **R18** `Checker` MUST report an argument name that is repeated in a function definition.

## Names

- **R19** `Checker` MUST report an imported name that is never used.
- **R20** `Checker` MUST report a name that is used but not defined, unless a `NameError` handler protects it.
