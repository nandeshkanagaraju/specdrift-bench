# tabulate specification

## Column alignment

- **R01** `tabulate` MUST align numeric columns with `numalign` and all other columns with `stralign`.
- **R02** `tabulate` MUST pad numbers aligned as `decimal` so that their decimal points line up.
- **R03** `tabulate` MUST let `colalign` override the alignment of an individual column.

## Missing values

- **R04** `tabulate` MUST replace a `None` value with `missingval`.

## Number formatting

- **R05** `tabulate` MUST format float values with `floatfmt`, which defaults to `g`.
- **R06** `tabulate` MUST format integer values with `intfmt`.

## Number parsing

- **R07** `tabulate` MUST treat a string that looks like a whole number as an integer.
- **R08** `tabulate` MUST keep the original text of a column when number parsing is disabled for it with `disable_numparse`.

## Input data

- **R09** `tabulate` MUST use the keys of a dict of columns as the headers when `headers="keys"`.
- **R10** `tabulate` MUST take the headers from the first row, leaving it out of the data, when `headers="firstrow"`.
- **R11** `tabulate` MUST build the columns of a list of dicts from the keys in first-seen order, with a missing key giving a `None` cell.
- **R12** `tabulate` MUST raise `TypeError` when the tabular data is not iterable.

## Row index

- **R13** `tabulate` MUST prepend a row-index column when `showindex="always"`.
- **R14** `tabulate` MUST raise `ValueError` when an explicit `showindex` sequence does not have one value per row.

## Edge cases

- **R15** `tabulate` MUST return an empty string for a table that has no headers and no rows.

## Separating lines

- **R16** `tabulate` MUST draw a horizontal line in place of a row that is `SEPARATING_LINE`.

## Custom formats

- **R17** `simple_separated_format` MUST return a format whose header and data rows join the cells with the given separator.

## Formats

- **R18** The `pipe` format MUST mark a right-aligned or decimal-aligned column with a trailing colon in its header line.
- **R19** The `html` format MUST escape the cell text.

## Wrapping

- **R20** `tabulate` MUST apply a single integer `maxcolwidths` to every column.
