import pytest
from tomli import TOMLDecodeError, loads


def test_a_key_defined_twice_raises():
    with pytest.raises(TOMLDecodeError):
        loads("a = 1\na = 2")


def test_the_same_key_in_two_tables_is_allowed():
    assert loads("[x]\na = 1\n[y]\na = 2") == {"x": {"a": 1}, "y": {"a": 2}}


def test_distinct_keys_in_one_table_are_allowed():
    assert loads("a = 1\nb = 2") == {"a": 1, "b": 2}
