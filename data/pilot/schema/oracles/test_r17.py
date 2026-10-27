import pytest
from schema import Schema


def test_a_reference_without_a_name_raises():
    with pytest.raises(ValueError):
        Schema(int, as_reference=True)


def test_a_reference_with_a_name_is_accepted():
    assert Schema(int, as_reference=True, name="n").as_reference is True


def test_a_non_reference_needs_no_name():
    assert Schema(int).as_reference is False
