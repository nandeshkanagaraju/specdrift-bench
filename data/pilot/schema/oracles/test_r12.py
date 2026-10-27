import pytest
from schema import Or, Schema, SchemaError, Use


def test_the_first_matching_alternative_returns_its_result():
    assert Schema(Or(Use(int), Use(str))).validate("5") == 5


def test_a_later_alternative_is_used_when_earlier_ones_fail():
    assert Schema(Or(int, str)).validate("a") == "a"


def test_no_matching_alternative_raises():
    with pytest.raises(SchemaError):
        Schema(Or(int, str)).validate(1.5)
