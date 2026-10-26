import pytest
from tomli import loads


def test_a_parse_float_that_returns_a_list_raises():
    with pytest.raises(ValueError):
        loads("a = 1.5", parse_float=list)


def test_a_parse_float_that_returns_a_str_is_accepted():
    assert loads("a = 1.5", parse_float=str) == {"a": "1.5"}
