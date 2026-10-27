import pytest
from schema import Schema, SchemaMissingKeyError


def test_two_missing_keys_use_the_plural():
    with pytest.raises(SchemaMissingKeyError) as info:
        Schema({"a": int, "b": int}).validate({})
    assert str(info.value) == "Missing keys: 'a', 'b'"


def test_one_missing_key_uses_the_singular():
    with pytest.raises(SchemaMissingKeyError) as info:
        Schema({"a": int}).validate({})
    assert str(info.value) == "Missing key: 'a'"
