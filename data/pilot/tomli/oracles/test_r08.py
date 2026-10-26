import pytest
from tomli import TOMLDecodeError, loads


def test_a_key_added_to_an_inline_table_raises():
    with pytest.raises(TOMLDecodeError):
        loads("a = {x = 1}\na.y = 2")


def test_a_dotted_key_added_to_a_dotted_table_is_allowed():
    assert loads("a.x = 1\na.y = 2") == {"a": {"x": 1, "y": 2}}
