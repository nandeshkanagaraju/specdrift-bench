import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_min_is_included_by_default():
    assert Range(min=1)(1) == 1
    assert Range(min=1)(2) == 2


def test_below_min():
    with pytest.raises(RangeInvalid):
        Range(min=1)(0)
