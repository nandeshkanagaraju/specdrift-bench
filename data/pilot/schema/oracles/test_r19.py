import pytest
from schema import Forbidden, Schema, SchemaForbiddenKeyError


def test_a_forbidden_key_raises():
    with pytest.raises(SchemaForbiddenKeyError):
        Schema({Forbidden("x"): int}).validate({"x": 1})


def test_data_without_the_forbidden_key_passes():
    assert Schema({Forbidden("x"): int, "y": int}).validate({"y": 1}) == {"y": 1}
