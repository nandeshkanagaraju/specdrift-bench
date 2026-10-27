import pytest
from schema import Schema, SchemaError


def test_every_element_is_validated():
    assert Schema([int]).validate([1, 2, 3]) == [1, 2, 3]


def test_an_invalid_element_raises():
    with pytest.raises(SchemaError):
        Schema([int]).validate([1, "x"])


def test_alternatives_in_the_list_are_all_allowed():
    assert Schema([int, str]).validate([1, "x"]) == [1, "x"]
