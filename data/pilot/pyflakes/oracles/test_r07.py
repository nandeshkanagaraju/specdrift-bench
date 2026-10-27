from io import StringIO

from pyflakes.reporter import Reporter


def test_line_column_and_message_are_written():
    err = StringIO()
    Reporter(StringIO(), err).syntaxError("f.py", "bad", 3, 5, None)
    assert err.getvalue() == "f.py:3:5: bad\n"


def test_the_column_is_left_out_when_the_offset_is_none():
    err = StringIO()
    Reporter(StringIO(), err).syntaxError("f.py", "bad", 3, None, None)
    assert err.getvalue() == "f.py:3: bad\n"


def test_a_line_number_below_one_is_written_as_one():
    err = StringIO()
    Reporter(StringIO(), err).syntaxError("f.py", "bad", 0, 2, None)
    assert err.getvalue() == "f.py:1:2: bad\n"


def test_the_source_line_and_a_caret_follow_when_text_is_given():
    err = StringIO()
    Reporter(StringIO(), err).syntaxError("f.py", "bad", 1, 5, "x = (")
    assert err.getvalue() == "f.py:1:5: bad\nx = (\n    ^\n"
