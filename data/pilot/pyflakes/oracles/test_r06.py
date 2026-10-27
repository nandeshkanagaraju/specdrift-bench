from io import StringIO

from pyflakes.reporter import Reporter


def test_the_filename_and_message_are_joined_by_a_colon():
    err = StringIO()
    Reporter(StringIO(), err).unexpectedError("f.py", "bad")
    assert err.getvalue() == "f.py: bad\n"


def test_nothing_is_written_to_the_warning_stream():
    out = StringIO()
    Reporter(out, StringIO()).unexpectedError("f.py", "bad")
    assert out.getvalue() == ""


def test_errors_accumulate_one_per_line():
    err = StringIO()
    reporter = Reporter(StringIO(), err)
    reporter.unexpectedError("a.py", "x")
    reporter.unexpectedError("b.py", "y")
    assert err.getvalue() == "a.py: x\nb.py: y\n"
