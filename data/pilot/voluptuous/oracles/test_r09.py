import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_too_long():
    with pytest.raises(LengthInvalid):
        Length(max=2)("abc")


def test_short_enough():
    assert Length(max=2)("ab") == "ab"
    assert Length(max=2)("a") == "a"
