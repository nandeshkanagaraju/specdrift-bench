from tomli import TOMLDecodeError


def test_an_error_on_the_first_line_has_line_one():
    assert TOMLDecodeError("bad", "a = 1", 2).lineno == 1


def test_an_error_after_one_newline_has_line_two():
    assert TOMLDecodeError("bad", "a = 1\nb = 2", 7).lineno == 2


def test_an_error_after_two_newlines_has_line_three():
    assert TOMLDecodeError("bad", "a\nb\nc", 4).lineno == 3
