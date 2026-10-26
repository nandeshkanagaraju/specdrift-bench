import pytest
from schema import Schema, SchemaError, Use


def test_use_returns_the_converted_value():
    assert Schema(Use(int)).validate("123") == 123


def test_use_wraps_a_failing_callable_in_a_schema_error():
    with pytest.raises(SchemaError):
        Schema(Use(int)).validate("x")
