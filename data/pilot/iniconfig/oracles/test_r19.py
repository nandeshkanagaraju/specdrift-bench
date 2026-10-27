from iniconfig._parse import parse_ini_data


def test_lines_after_an_empty_value_are_joined_with_newlines():
    result = parse_ini_data("p", "[s]\nk=\n  a\n  b\n", strip_inline_comments=True)
    assert result[0] == {"s": {"k": "a\nb"}}


def test_lines_after_a_first_line_are_joined_with_newlines():
    result = parse_ini_data("p", "[s]\nk=x\n  y\n", strip_inline_comments=True)
    assert result[0] == {"s": {"k": "x\ny"}}
