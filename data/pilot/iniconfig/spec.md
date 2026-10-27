# iniconfig specification

## Parse errors

- **R01** `IniConfig.parse` MUST raise `ParseError` when two sections have the same name.
- **R02** `IniConfig.parse` MUST raise `ParseError` when a name occurs twice inside one section.
- **R03** `IniConfig.parse` MUST raise `ParseError` for a key line that appears before any section header.
- **R04** `IniConfig.parse` MUST raise `ParseError` for a section header with an empty name.
- **R05** `IniConfig.parse` MUST raise `ParseError` for an indented line that directly follows a section header.
- **R06** `IniConfig.parse` MUST raise `ParseError` for a non-indented line that contains neither `=` nor `:`.

## Inline comments

- **R07** `IniConfig.parse` MUST strip inline comments from values by default.
- **R08** `IniConfig.__init__` MUST keep inline comments in values when it parses the data itself.

## Section names

- **R09** `IniConfig.parse` MUST NOT strip whitespace from section names unless `strip_section_whitespace` is true.
- **R10** `IniConfig.parse` MUST read the text between `[` and `]` as the section name.

## Line numbers

- **R11** `IniConfig.lineof` MUST return line numbers counted from 1.
- **R12** `ParseError.__str__` MUST print `lineno` plus one as the line number.

## Lookup

- **R13** `IniConfig.get` MUST return `default` when the section or the name does not exist.
- **R14** `IniConfig.get` MUST pass the stored value through `convert` when `convert` is given.
- **R15** `IniConfig.__getitem__` MUST raise `KeyError` for a section name that does not exist.

## Ordering

- **R16** `IniConfig.__iter__` MUST yield sections in the order they appear in the file.
- **R17** `SectionWrapper.__iter__` MUST yield names in the order they appear in the file.

## Value syntax

- **R18** `IniConfig.parse` MUST ignore a leading UTF-8 byte order mark in the data.
- **R19** `IniConfig.parse` MUST join the lines of a multi-line value with newline characters.
- **R20** `IniConfig.parse` MUST keep an `=` that follows the key-value separator inside the value.
