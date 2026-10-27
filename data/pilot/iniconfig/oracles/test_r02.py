import pytest
from iniconfig import ParseError
from iniconfig._parse import parse_ini_data


def test_a_repeated_name_in_one_section_raises():
    with pytest.raises(ParseError):
        parse_ini_data("p", "[a]\nk=1\nk=2\n", strip_inline_comments=True)


def test_the_same_name_in_two_sections_is_allowed():
    result = parse_ini_data("p", "[a]\nk=1\n[b]\nk=2\n", strip_inline_comments=True)
    assert result[0] == {"a": {"k": "1"}, "b": {"k": "2"}}
