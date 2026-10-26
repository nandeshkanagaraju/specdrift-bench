from iniconfig import ParseError


def test_line_zero_is_printed_as_line_one():
    assert str(ParseError("p", 0, "bad")) == "p:1: bad"


def test_line_four_is_printed_as_line_five():
    assert str(ParseError("q.ini", 4, "worse")) == "q.ini:5: worse"
