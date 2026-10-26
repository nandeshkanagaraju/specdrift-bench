import pytest
from tomli import loads


def test_bytes_are_not_accepted():
    with pytest.raises(TypeError):
        loads(b"a = 1")


def test_an_integer_is_not_accepted():
    with pytest.raises(TypeError):
        loads(1)


def test_a_str_is_accepted():
    assert loads("a = 1") == {"a": 1}
