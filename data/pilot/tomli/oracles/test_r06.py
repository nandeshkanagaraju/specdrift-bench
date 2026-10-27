import pytest
from tomli import TOMLDecodeError, loads


def test_the_same_table_header_twice_raises():
    with pytest.raises(TOMLDecodeError):
        loads("[a]\n[a]")


def test_a_header_naming_an_inline_table_raises():
    with pytest.raises(TOMLDecodeError):
        loads("a = {x = 1}\n[a]")


def test_two_different_table_headers_parse():
    assert loads("[a]\n[b]") == {"a": {}, "b": {}}
