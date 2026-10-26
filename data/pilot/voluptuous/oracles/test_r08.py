import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_too_short():
    with pytest.raises(LengthInvalid):
        Length(min=2)("a")


def test_long_enough():
    assert Length(min=2)("ab") == "ab"
    assert Length(min=2)("abc") == "abc"
