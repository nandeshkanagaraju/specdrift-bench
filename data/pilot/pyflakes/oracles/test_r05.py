from io import StringIO

from pyflakes.reporter import Reporter


def test_a_message_is_followed_by_a_newline():
    out = StringIO()
    Reporter(out, StringIO()).flake("hi")
    assert out.getvalue() == "hi\n"


def test_messages_accumulate_one_per_line():
    out = StringIO()
    reporter = Reporter(out, StringIO())
    reporter.flake("a")
    reporter.flake("b")
    assert out.getvalue() == "a\nb\n"


def test_nothing_is_written_to_the_error_stream():
    err = StringIO()
    Reporter(StringIO(), err).flake("hi")
    assert err.getvalue() == ""
