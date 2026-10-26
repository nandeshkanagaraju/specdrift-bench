from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_a_repeated_argument_is_reported():
    out = StringIO()
    count = check('def f(a, a):\n    pass\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: duplicate argument 'a' in function definition\n"
    assert count == 1


def test_a_repeated_lambda_argument_is_reported():
    out = StringIO()
    count = check('lambda a, a: 0\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: duplicate argument 'a' in function definition\n"
    assert count == 1


def test_distinct_arguments_are_fine():
    out = StringIO()
    count = check('def f(a, b):\n    pass\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
