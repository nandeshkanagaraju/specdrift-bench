import pytest
from schema import Schema, SchemaMissingKeyError


def test_an_absent_required_key_raises():
    with pytest.raises(SchemaMissingKeyError):
        Schema({"a": int}).validate({})


def test_a_present_required_key_passes():
    assert Schema({"a": int}).validate({"a": 1}) == {"a": 1}
