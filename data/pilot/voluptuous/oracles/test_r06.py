import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_below_min_gives_min():
    assert Clamp(min=0, max=1)(-1) == 0
    assert Clamp(min=0, max=1)(0) == 0
    assert Clamp(min=0)(5) == 5
