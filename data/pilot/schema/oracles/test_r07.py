import pytest
from schema import Schema, SchemaWrongKeyError


def test_an_extra_key_raises():
    with pytest.raises(SchemaWrongKeyError):
        Schema({"a": int}).validate({"a": 1, "b": 2})


def test_an_extra_key_is_dropped_when_extra_keys_are_ignored():
    assert Schema({"a": int}, ignore_extra_keys=True).validate({"a": 1, "b": 2}) == {"a": 1}


def test_no_extra_key_passes():
    assert Schema({"a": int}).validate({"a": 1}) == {"a": 1}
