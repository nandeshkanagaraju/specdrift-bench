from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_continue_outside_a_loop_is_reported():
    out = StringIO()
    count = check('continue\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: 'continue' not properly in loop\n"
    assert count == 1


def test_continue_in_a_loop_is_fine():
    out = StringIO()
    count = check('for i in range(3):\n    continue\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0


def test_continue_in_the_else_of_a_loop_is_reported():
    out = StringIO()
    count = check('for i in []:\n    pass\nelse:\n    continue\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:4:5: 'continue' not properly in loop\n"
    assert count == 1
