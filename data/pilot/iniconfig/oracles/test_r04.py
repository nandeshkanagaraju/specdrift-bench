import pytest
from iniconfig import ParseError
from iniconfig._parse import parse_lines


def test_an_empty_section_name_raises():
    with pytest.raises(ParseError):
        parse_lines("p", ["[]\n"])


def test_a_non_empty_section_name_is_accepted():
    result = parse_lines("p", ["[a]\n"])
    assert result == [(0, "a", None, None)]
