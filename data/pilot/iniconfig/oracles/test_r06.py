import pytest
from iniconfig import ParseError
from iniconfig._parse import _parseline


def test_a_line_with_no_separator_raises():
    with pytest.raises(ParseError):
        _parseline("p", "foo\n", 0, True, False)


def test_equals_is_a_separator():
    assert _parseline("p", "k=v\n", 0, True, False) == ("k", "v")


def test_colon_is_a_separator():
    assert _parseline("p", "k:v\n", 0, True, False) == ("k", "v")
