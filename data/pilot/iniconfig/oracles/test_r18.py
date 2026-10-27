from iniconfig._parse import parse_ini_data


def test_a_leading_byte_order_mark_is_ignored():
    result = parse_ini_data("p", "﻿[a]\nk=v\n", strip_inline_comments=True)
    assert result[0] == {"a": {"k": "v"}}


def test_the_same_data_without_a_mark_gives_the_same_result():
    result = parse_ini_data("p", "[a]\nk=v\n", strip_inline_comments=True)
    assert result[0] == {"a": {"k": "v"}}
