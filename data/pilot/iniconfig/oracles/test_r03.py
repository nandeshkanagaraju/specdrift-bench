import pytest
from iniconfig import ParseError
from iniconfig._parse import parse_ini_data


def test_a_key_before_any_section_raises():
    with pytest.raises(ParseError):
        parse_ini_data("p", "k=1\n[a]\n", strip_inline_comments=True)


def test_a_key_after_a_section_header_is_accepted():
    result = parse_ini_data("p", "[a]\nk=1\n", strip_inline_comments=True)
    assert result[0] == {"a": {"k": "1"}}
