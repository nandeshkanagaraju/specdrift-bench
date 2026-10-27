import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_true_words():
    assert Schema(Boolean())("1") is True
    assert Schema(Boolean())("true") is True
    assert Schema(Boolean())("YES") is True
    assert Schema(Boolean())("On") is True
    assert Schema(Boolean())("ENABLE") is True
