import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_false_words():
    assert Schema(Boolean())("0") is False
    assert Schema(Boolean())("false") is False
    assert Schema(Boolean())("NO") is False
    assert Schema(Boolean())("Off") is False
    assert Schema(Boolean())("DISABLE") is False
