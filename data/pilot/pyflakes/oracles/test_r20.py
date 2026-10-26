from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_an_undefined_name_is_reported():
    out = StringIO()
    count = check('foo\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: undefined name 'foo'\n"
    assert count == 1


def test_a_defined_name_is_fine():
    out = StringIO()
    count = check('foo = 1\nfoo\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0


def test_a_name_error_handler_protects_the_use():
    out = StringIO()
    count = check('try:\n    foo\nexcept NameError:\n    pass\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
