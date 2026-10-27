from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_is_against_a_string_is_reported():
    out = StringIO()
    count = check("x = 1\nx is 'a'\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == 't:2:1: use ==/!= to compare constant literals (str, bytes, int, float, tuple)\n'
    assert count == 1


def test_is_not_against_a_number_is_reported():
    out = StringIO()
    count = check('x = 1\nx is not 1\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == 't:2:1: use ==/!= to compare constant literals (str, bytes, int, float, tuple)\n'
    assert count == 1


def test_is_against_none_is_fine():
    out = StringIO()
    count = check('x = 1\nx is None\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
