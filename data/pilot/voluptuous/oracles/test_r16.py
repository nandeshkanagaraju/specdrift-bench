import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_non_strings():
    with pytest.raises(MatchInvalid):
        Match("a")(123)
    with pytest.raises(MatchInvalid):
        Match("a")(None)


def test_a_string_is_fine():
    assert Match("a")("a") == "a"
