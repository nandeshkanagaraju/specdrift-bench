import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_output_feeds_the_next_validator():
    assert Schema(All(Coerce(int), Range(min=1, max=10)))("5") == 5


def test_later_validator_sees_the_coerced_value():
    with pytest.raises(MultipleInvalid):
        Schema(All(Coerce(int), Range(max=3)))("5")
