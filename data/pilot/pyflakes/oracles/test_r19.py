from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_an_unused_import_is_reported():
    out = StringIO()
    count = check('import os\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: 'os' imported but unused\n"
    assert count == 1


def test_each_unused_import_is_reported_in_line_order():
    out = StringIO()
    count = check('import os\nimport sys\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:1: 'os' imported but unused\nt:2:1: 'sys' imported but unused\n"
    assert count == 2


def test_a_used_import_is_fine():
    out = StringIO()
    count = check('import os\nos\n', "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
