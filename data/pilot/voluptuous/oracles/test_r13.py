import pytest
from voluptuous import (
    All, Any, Boolean, BooleanInvalid, Clamp, Coerce, Email, FalseInvalid, IsFalse, Length, LengthInvalid,
    Match, MatchInvalid, MultipleInvalid, Range, RangeInvalid, Schema,
)


def test_false_values_pass():
    assert Schema(IsFalse())([]) == []
    assert Schema(IsFalse())(0) == 0


def test_true_values_fail():
    with pytest.raises(MultipleInvalid):
        Schema(IsFalse())(True)
    with pytest.raises(MultipleInvalid):
        Schema(IsFalse())([1])
