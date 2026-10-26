import pytest
from schema import Const, Schema, SchemaError, Use


def test_const_returns_the_original_data():
    assert Schema(Const(Use(int))).validate("5") == "5"


def test_const_still_validates():
    with pytest.raises(SchemaError):
        Schema(Const(int)).validate("x")
