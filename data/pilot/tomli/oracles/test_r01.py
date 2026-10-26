import pytest
from tomli import TOMLDecodeError, loads


def test_a_closing_bracket_cannot_begin_a_statement():
    with pytest.raises(TOMLDecodeError):
        loads("]] this is invalid TOML [[")


def test_an_equals_sign_cannot_begin_a_statement():
    with pytest.raises(TOMLDecodeError):
        loads("= 1")


def test_a_comment_can_begin_a_line():
    assert loads("# note\na = 1") == {"a": 1}


def test_a_key_can_begin_a_statement():
    assert loads("a = 1") == {"a": 1}
