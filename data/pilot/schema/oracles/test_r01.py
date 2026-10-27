import pytest
from schema import Schema, SchemaUnexpectedTypeError


def test_a_bool_is_rejected_by_an_int_schema():
    with pytest.raises(SchemaUnexpectedTypeError):
        Schema(int).validate(True)


def test_an_int_is_accepted_by_an_int_schema():
    assert Schema(int).validate(1) == 1


def test_a_bool_is_accepted_by_a_bool_schema():
    assert Schema(bool).validate(True) is True
