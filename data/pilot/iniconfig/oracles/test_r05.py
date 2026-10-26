import pytest
from iniconfig import ParseError
from iniconfig._parse import parse_lines


def test_an_indented_line_right_after_a_header_raises():
    with pytest.raises(ParseError):
        parse_lines("p", ["[a]\n", "  x\n"])


def test_an_indented_line_after_a_key_continues_its_value():
    result = parse_lines("p", ["[a]\n", "k=\n", "  x\n"])
    assert result == [(0, "a", None, None), (1, "a", "k", ["x"])]
