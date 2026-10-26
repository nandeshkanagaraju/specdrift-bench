from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_assert_of_a_tuple_is_reported():
    out = StringIO()
    count = check("assert (1, 'msg')\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == 't:1:1: assertion is always true, perhaps remove parentheses?\n'
    assert count == 1


def test_assert_of_an_empty_tuple_is_fine():
    out = StringIO()
    count = check('assert ()\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0


def test_assert_with_a_message_is_fine():
    out = StringIO()
    count = check("assert 1, 'msg'\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
