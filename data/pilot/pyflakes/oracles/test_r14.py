from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_raising_the_bare_name_is_reported():
    out = StringIO()
    count = check('raise NotImplemented\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: 'raise NotImplemented' should be 'raise NotImplementedError'\n"
    assert count == 1


def test_raising_a_call_of_the_name_is_reported():
    out = StringIO()
    count = check("raise NotImplemented('x')\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: 'raise NotImplemented' should be 'raise NotImplementedError'\n"
    assert count == 1


def test_raising_the_error_class_is_fine():
    out = StringIO()
    count = check('raise NotImplementedError\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
