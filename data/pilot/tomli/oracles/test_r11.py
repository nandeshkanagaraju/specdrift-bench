from tomli import loads


def test_crlf_inside_a_multiline_string_becomes_lf():
    assert loads('a = """x\r\ny"""') == {"a": "x\ny"}


def test_crlf_between_statements_is_a_line_break():
    assert loads("a = 1\r\nb = 2\r\n") == {"a": 1, "b": 2}
