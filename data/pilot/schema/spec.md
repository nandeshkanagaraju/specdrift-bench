# schema specification

## Types and values

- **R01** `Schema(int)` MUST reject a `bool` value.
- **R02** `Schema` MUST raise `SchemaUnexpectedTypeError` when a value is not an instance of the schema's type.
- **R03** `Schema` MUST raise `SchemaError` when a callable schema returns a false value for the data.
- **R04** `Schema` MUST accept a plain value only when it equals the schema value.

## Lists and dicts

- **R05** `Schema` MUST validate every element of a list against the alternatives in a list schema.
- **R06** `Schema` MUST raise `SchemaMissingKeyError` when a required key of a dict schema is absent from the data.
- **R07** `Schema` MUST raise `SchemaWrongKeyError` for a key the dict schema does not allow unless `ignore_extra_keys` is true.
- **R08** `Schema` MUST NOT require a key wrapped in `Optional`.
- **R09** `Schema` MUST add the default of an `Optional` key that is absent from the data.
- **R10** `Schema` MUST write `Missing keys` in the plural when more than one key is missing.

## Combinators

- **R11** `And` MUST apply each of its schemas to the data in order and return the result of the last one.
- **R12** `Or` MUST return the result of the first alternative that accepts the data.

## Validators

- **R13** `Regex` MUST accept a string only when the pattern is found somewhere in it.
- **R14** `Use` MUST return the result of calling its callable on the data.
- **R15** `Use` MUST raise `TypeError` when given something that is not callable.
- **R16** `Const` MUST validate the data but return it unchanged.

## Other behaviour

- **R17** `Schema` MUST raise `ValueError` when `as_reference` is true and no name is given.
- **R18** `Schema.is_valid` MUST return `True` for valid data and `False` for invalid data.
- **R19** `Forbidden` MUST raise `SchemaForbiddenKeyError` when its key is present in the data.
- **R20** `SchemaError` MUST remove duplicate messages from its combined message.
