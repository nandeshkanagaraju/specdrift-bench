import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_unknown_words():
    with pytest.raises(MultipleInvalid):
        Schema(Boolean())("moo")
    with pytest.raises(MultipleInvalid):
        Schema(Boolean())("")
    with pytest.raises(MultipleInvalid):
        Schema(Boolean())("maybe")


def test_known_word_still_works():
    assert Schema(Boolean())("yes") is True
