from io import StringIO

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_each_occurrence_of_a_repeated_key_is_reported():
    out = StringIO()
    count = check("{'a': 1, 'a': 2}\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == "t:1:2: dictionary key 'a' repeated with different values\nt:1:10: dictionary key 'a' repeated with different values\n"
    assert count == 2


def test_a_repeated_key_with_the_same_value_is_fine():
    out = StringIO()
    count = check("{'a': 1, 'a': 1}\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0


def test_three_occurrences_with_one_odd_value_are_all_reported():
    out = StringIO()
    count = check("{'a': 1, 'a': 1, 'a': 2}\n", "t", Reporter(out, StringIO()))
    assert count == 3


def test_distinct_keys_are_fine():
    out = StringIO()
    count = check("{'a': 1, 'b': 2}\n", "t", Reporter(out, StringIO()))
    assert out.getvalue() == ''
    assert count == 0
