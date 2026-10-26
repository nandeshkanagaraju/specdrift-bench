import pytest
from schema import Schema, SchemaError


def test_an_equal_value_is_accepted():
    assert Schema(5).validate(5) == 5


def test_a_different_value_raises():
    with pytest.raises(SchemaError):
        Schema(5).validate(6)


def test_a_string_literal_is_matched_exactly():
    assert Schema("a").validate("a") == "a"
