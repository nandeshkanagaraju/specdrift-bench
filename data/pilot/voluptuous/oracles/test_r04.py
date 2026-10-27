import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_equal_to_an_excluded_max():
    with pytest.raises(RangeInvalid):
        Range(max=10, max_included=False)(10)


def test_below_an_excluded_max():
    assert Range(max=10, max_included=False)(9) == 9
