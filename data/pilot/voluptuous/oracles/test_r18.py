import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_no_at_sign():
    with pytest.raises(MultipleInvalid):
        Schema(Email())("a.com")
    with pytest.raises(MultipleInvalid):
        Schema(Email())("")


def test_plain_address():
    assert Schema(Email())("t@x.com") == "t@x.com"
