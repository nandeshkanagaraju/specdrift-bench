from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_clean_source_has_no_warnings():
    out = StringIO()
    count = check('x = 1\n', "t", Reporter(out, StringIO()))
    assert count == 0


def test_each_unused_import_counts_once():
    out = StringIO()
    count = check('import os\nimport sys\n', "t", Reporter(out, StringIO()))
    assert count == 2


def test_three_warnings_give_three():
    out = StringIO()
    count = check('import os\nimport sys\nimport re\n', "t", Reporter(out, StringIO()))
    assert count == 3
