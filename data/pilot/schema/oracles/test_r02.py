import pytest
from schema import Schema, SchemaUnexpectedTypeError


def test_a_string_is_rejected_by_an_int_schema():
    with pytest.raises(SchemaUnexpectedTypeError):
        Schema(int).validate("x")


def test_a_string_is_accepted_by_a_str_schema():
    assert Schema(str).validate("x") == "x"
