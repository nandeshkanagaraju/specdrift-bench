# tomli specification

## Syntax errors

- **R01** `loads` MUST raise `TOMLDecodeError` for a line that starts with a character that cannot begin a statement.
- **R02** `loads` MUST raise `TOMLDecodeError` when a statement is followed by anything other than a newline or the end of the document.
- **R03** `loads` MUST raise `TOMLDecodeError` for an array whose elements are not separated by commas.
- **R04** `loads` MUST raise `TOMLDecodeError` for a basic string that has no closing quote.

## Duplicates

- **R05** `loads` MUST raise `TOMLDecodeError` when a key is defined twice in the same table.
- **R06** `loads` MUST raise `TOMLDecodeError` when the same table header appears twice.
- **R07** `loads` MUST raise `TOMLDecodeError` for a repeated key inside one inline table.

## Inline tables

- **R08** `loads` MUST raise `TOMLDecodeError` when a key is added to an inline table after its definition.

## Arguments

- **R09** `loads` MUST raise `TypeError` when its argument is not a `str`.
- **R10** `load` MUST raise `TypeError` for a file object opened in text mode.
- **R11** `loads` MUST read `\r\n` line endings as `\n`.

## Floats

- **R12** `loads` MUST convert a TOML float with `parse_float` when one is given.
- **R13** `loads` MUST raise `ValueError` when `parse_float` returns a `dict` or a `list`.

## Integers

- **R14** `loads` MUST read `0x`, `0o` and `0b` prefixed integers in base 16, 8 and 2.

## String escapes

- **R15** `loads` MUST read `\u` followed by four hex digits as one Unicode character.
- **R16** `loads` MUST raise `TOMLDecodeError` for a `\u` escape that names a surrogate code point.

## Dates and times

- **R17** `loads` MUST read a date-time that ends in `Z` as a UTC time.
- **R18** `loads` MUST give a date-time with a `-` offset a negative UTC offset.

## Arrays of tables

- **R19** `loads` MUST add a new table to the list for each `[[name]]` header.

## Error position

- **R20** `TOMLDecodeError` MUST count `lineno` from 1.
