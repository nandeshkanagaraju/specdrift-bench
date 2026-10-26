from tomli import loads


def test_parse_float_receives_the_float_text():
    assert loads("a = 1.5", parse_float=str) == {"a": "1.5"}


def test_parse_float_also_receives_exponent_floats():
    assert loads("a = 1e3", parse_float=str) == {"a": "1e3"}


def test_integers_are_not_passed_to_parse_float():
    assert loads("a = 1", parse_float=str) == {"a": 1}
