import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_equal_to_an_excluded_min():
    with pytest.raises(RangeInvalid):
        Range(min=1, min_included=False)(1)


def test_above_an_excluded_min():
    assert Range(min=1, min_included=False)(2) == 2
