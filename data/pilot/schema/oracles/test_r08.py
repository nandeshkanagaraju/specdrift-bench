import pytest
from schema import Optional, Schema, SchemaMissingKeyError


def test_an_absent_optional_key_is_accepted():
    assert Schema({"a": int, Optional("b"): int}).validate({"a": 1}) == {"a": 1}


def test_a_present_optional_key_is_kept():
    assert Schema({"a": int, Optional("b"): int}).validate({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_an_absent_required_key_still_raises():
    with pytest.raises(SchemaMissingKeyError):
        Schema({"a": int, Optional("b"): int}).validate({"b": 2})
