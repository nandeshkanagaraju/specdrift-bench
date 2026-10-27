import pytest
from tomli import TOMLDecodeError, loads


def test_a_string_with_no_closing_quote_raises():
    with pytest.raises(TOMLDecodeError):
        loads('a = "abc')


def test_a_closed_string_parses():
    assert loads('a = "abc"') == {"a": "abc"}
