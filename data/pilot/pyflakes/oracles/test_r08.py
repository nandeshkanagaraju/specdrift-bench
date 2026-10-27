from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_return_at_module_level_is_reported():
    out = StringIO()
    count = check('return 1\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: 'return' outside function\n"
    assert count == 1


def test_return_in_a_class_body_is_reported():
    out = StringIO()
    count = check('class C:\n    return 1\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:2:5: 'return' outside function\n"
    assert count == 1


def test_return_in_a_function_is_fine():
    out = StringIO()
    count = check('def f():\n    return 1\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
