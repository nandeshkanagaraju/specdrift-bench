import pytest
from iniconfig import ParseError
from iniconfig._parse import parse_ini_data


def test_two_sections_with_the_same_name_raise():
    with pytest.raises(ParseError):
        parse_ini_data("p", "[a]\n[a]\n", strip_inline_comments=True)


def test_two_sections_with_different_names_do_not_raise():
    result = parse_ini_data("p", "[a]\n[b]\n", strip_inline_comments=True)
    assert result[0] == {"a": {}, "b": {}}
