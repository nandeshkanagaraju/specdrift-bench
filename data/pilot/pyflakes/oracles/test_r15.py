from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_an_f_string_without_placeholders_is_reported():
    out = StringIO()
    count = check("f'abc'\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == 't:1:1: f-string is missing placeholders\n'
    assert count == 1


def test_an_f_string_with_a_placeholder_is_fine():
    out = StringIO()
    count = check("x = 1\nf'{x}'\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0


def test_a_format_spec_is_not_reported():
    out = StringIO()
    count = check("x = 1\nf'{x:>5}'\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0


def test_a_plain_string_is_fine():
    out = StringIO()
    count = check("'abc'\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
