# xmltodict specification

## Parsing structure

- **R01** `parse` MUST prefix attribute names with `@` by default.
- **R02** `parse` MUST collect sibling elements with the same tag into a list.
- **R03** `parse` MUST wrap a single child element in a list when its tag is named in `force_list`.
- **R04** `parse` MUST store the text of every element under `#text` when `force_cdata` is true.
- **R05** `parse` MUST drop element attributes when `xml_attribs` is false.
- **R06** `parse` MUST strip surrounding whitespace from element text by default.

## Namespaces

- **R07** `parse` MUST replace a namespace URI with its prefix from `namespaces` when `process_namespaces` is true.
- **R08** `parse` MUST leave namespace prefixes in tag names unchanged unless `process_namespaces` is true.

## Safety

- **R09** `parse` MUST raise `ValueError` for a document that declares an entity unless `disable_entities` is false.

## Comments

- **R10** `parse` MUST add comments under `#comment` only when `process_comments` is true.

## Streaming

- **R11** `parse` MUST raise `ParsingInterrupted` when `item_callback` returns a false value.

## Document output

- **R12** `unparse` MUST start a full document with an XML declaration.
- **R13** `unparse` MUST raise `ValueError` for a full document that has more than one root.
- **R14** `unparse` MUST raise `ValueError` for a full document that has no root.

## Value output

- **R15** `unparse` MUST write keys that start with `@` as attributes of their element.
- **R16** `unparse` MUST write boolean values as lowercase `true` and `false`.
- **R17** `unparse` MUST raise `ValueError` for an element name that contains `<` or `>`.
- **R18** `unparse` MUST indent each nesting level with a tab when `pretty` is true.
- **R19** `unparse` MUST omit the element for an empty list.
- **R20** `unparse` MUST raise `ValueError` for a `bytes_errors` handler that does not exist.
