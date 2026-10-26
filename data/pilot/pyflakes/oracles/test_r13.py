from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_if_of_a_tuple_is_reported():
    out = StringIO()
    count = check('if (1, 2):\n    pass\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: 'if tuple literal' is always true, perhaps remove accidental comma?\n"
    assert count == 1


def test_if_of_an_empty_tuple_is_fine():
    out = StringIO()
    count = check('if ():\n    pass\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0


def test_if_of_a_number_is_fine():
    out = StringIO()
    count = check('if 1:\n    pass\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
