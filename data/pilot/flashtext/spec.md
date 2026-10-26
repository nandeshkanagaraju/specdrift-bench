# flashtext specification

## Adding keywords

- **R01** `add_keyword` MUST return `True` for a new keyword and `False` for one that is already present.
- **R02** `add_keyword` MUST store keywords in lowercase unless `case_sensitive` is true.
- **R03** `add_keyword` MUST use the keyword itself as the clean name when none is given.
- **R04** `add_keywords_from_dict` MUST raise `AttributeError` when a value is not a list.
- **R05** `add_keywords_from_list` MUST raise `AttributeError` when its argument is not a list.

## Counting and lookup

- **R06** `len` of a `KeywordProcessor` MUST count each distinct keyword once.
- **R07** `in` MUST be true only for a complete keyword and not for a prefix of one.
- **R08** `get_keyword` MUST return the clean name mapped to a keyword.
- **R09** `get_all_keywords` MUST map each stored keyword to its clean name.

## Removing keywords

- **R10** `remove_keyword` MUST return `True` when it removes a keyword and `False` when the keyword is absent.
- **R11** `remove_keyword` MUST keep other keywords that share a prefix with the removed one.
- **R12** `remove_keyword` MUST decrease the keyword count by one when it removes a keyword.

## Iteration

- **R13** Iterating over a `KeywordProcessor` MUST raise `NotImplementedError`.

## Extraction

- **R14** `extract_keywords` MUST return the clean name of each keyword found, in the order found.
- **R15** `extract_keywords` MUST return (clean name, start, end) tuples when `span_info` is true.
- **R16** `extract_keywords` MUST return an empty list for an empty sentence.
- **R17** `extract_keywords` MUST ignore case unless `case_sensitive` is true.
- **R18** `get_next_word` MUST return the leading characters of a sentence up to the first non-word character.

## Replacement

- **R19** `replace_keywords` MUST replace each keyword with its clean name.
- **R20** `replace_keywords` MUST return an empty sentence unchanged.
