from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_a_syntax_error_gives_one():
    assert check("x = (\n", "t", Reporter(StringIO(), StringIO())) == 1


def test_a_syntax_error_goes_to_the_error_stream():
    out = StringIO()
    err = StringIO()
    check("x = (\n", "t", Reporter(out, err))
    assert out.getvalue() == ""
    assert err.getvalue()[:2] == "t:"


def test_valid_source_writes_no_error():
    err = StringIO()
    check("x = 1\n", "t", Reporter(StringIO(), err))
    assert err.getvalue() == ""
