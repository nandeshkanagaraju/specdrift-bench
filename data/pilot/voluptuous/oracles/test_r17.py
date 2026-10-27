import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_pattern_is_not_searched():
    with pytest.raises(MatchInvalid):
        Match("b")("ab")


def test_pattern_at_the_start():
    assert Match("a")("ab") == "ab"
