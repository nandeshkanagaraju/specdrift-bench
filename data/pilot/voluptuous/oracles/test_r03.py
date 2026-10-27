import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_max_is_included_by_default():
    assert Range(max=10)(10) == 10
    assert Range(max=10)(9) == 9


def test_above_max():
    with pytest.raises(RangeInvalid):
        Range(max=10)(11)
