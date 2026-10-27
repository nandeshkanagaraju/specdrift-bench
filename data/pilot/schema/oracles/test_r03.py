import pytest
from schema import Schema, SchemaError


def test_a_callable_returning_false_raises():
    with pytest.raises(SchemaError):
        Schema(str.isdigit).validate("abc")


def test_a_callable_returning_true_passes_the_data_through():
    assert Schema(str.isdigit).validate("123") == "123"
