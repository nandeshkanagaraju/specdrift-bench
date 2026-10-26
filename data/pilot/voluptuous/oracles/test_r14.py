import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_first_accepting_validator_wins():
    assert Schema(Any(Coerce(int), str))("5") == 5
    assert Schema(Any(int, str))("x") == "x"


def test_no_validator_accepts():
    with pytest.raises(MultipleInvalid):
        Schema(Any(int, float))("x")
