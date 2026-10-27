import pytest
from schema import And, Schema, SchemaError, Use


def test_all_schemas_are_applied_in_order():
    assert Schema(And(Use(int), Use(str), Use(len))).validate("123") == 3


def test_a_failing_schema_raises():
    with pytest.raises(SchemaError):
        Schema(And(str, str.isdigit)).validate("ab")


def test_all_passing_schemas_return_the_data():
    assert Schema(And(str, str.isdigit)).validate("12") == "12"
