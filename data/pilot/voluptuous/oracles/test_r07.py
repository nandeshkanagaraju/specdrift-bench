import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_above_max_gives_max():
    assert Clamp(min=0, max=1)(5) == 1
    assert Clamp(min=0, max=1)(1) == 1
    assert Clamp(max=1)(-5) == -5
