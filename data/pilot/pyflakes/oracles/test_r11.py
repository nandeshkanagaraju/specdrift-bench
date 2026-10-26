from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_break_outside_a_loop_is_reported():
    out = StringIO()
    count = check('break\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: 'break' outside loop\n"
    assert count == 1


def test_break_in_a_loop_is_fine():
    out = StringIO()
    count = check('while True:\n    break\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0


def test_break_in_the_else_of_a_loop_is_reported():
    out = StringIO()
    count = check('for i in []:\n    pass\nelse:\n    break\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:4:5: 'break' outside loop\n"
    assert count == 1
