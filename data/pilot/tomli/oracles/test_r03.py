import pytest
from tomli import TOMLDecodeError, loads


def test_two_array_elements_without_a_comma_raise():
    with pytest.raises(TOMLDecodeError):
        loads("a = [1 2]")


def test_array_elements_separated_by_commas_parse():
    assert loads("a = [1, 2]") == {"a": [1, 2]}


def test_an_empty_array_parses():
    assert loads("a = []") == {"a": []}
