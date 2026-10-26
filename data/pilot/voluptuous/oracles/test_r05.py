import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_none_has_no_ordering():
    with pytest.raises(RangeInvalid):
        Range(min=1)(None)


def test_text_has_no_ordering():
    with pytest.raises(RangeInvalid):
        Range(max=3)("a")


def test_numbers_are_fine():
    assert Range(min=1, max=3)(2) == 2
