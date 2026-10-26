import pytest
from tomli import TOMLDecodeError, loads


def test_text_after_a_value_on_the_same_line_raises():
    with pytest.raises(TOMLDecodeError):
        loads("a = 1 b = 2")


def test_two_statements_on_separate_lines_parse():
    assert loads("a = 1\nb = 2") == {"a": 1, "b": 2}


def test_a_statement_at_the_end_of_the_document_parses():
    assert loads("a = 1") == {"a": 1}
