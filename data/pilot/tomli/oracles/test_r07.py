import pytest
from tomli import TOMLDecodeError, loads


def test_a_repeated_key_in_an_inline_table_raises():
    with pytest.raises(TOMLDecodeError):
        loads("a = {x = 1, x = 2}")


def test_distinct_keys_in_an_inline_table_parse():
    assert loads("a = {x = 1, y = 2}") == {"a": {"x": 1, "y": 2}}
