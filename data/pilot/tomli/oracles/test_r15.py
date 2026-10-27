from tomli import loads


def test_u_escape_reads_four_hex_digits():
    assert loads('a = "\\u0041"') == {"a": "A"}


def test_u_escape_is_followed_by_ordinary_text():
    assert loads('a = "\\u0042x"') == {"a": "Bx"}
