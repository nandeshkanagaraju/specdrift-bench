import pytest
from tabulate import tabulate


def test_too_few_index_values_raise_a_value_error():
    with pytest.raises(ValueError):
        tabulate([["a"], ["b"]], showindex=["x"])


def test_too_many_index_values_raise_a_value_error():
    with pytest.raises(ValueError):
        tabulate([["a"]], showindex=["x", "y"])


def test_one_index_value_per_row_is_accepted():
    assert tabulate([["a"], ["b"]], showindex=["x", "y"], tablefmt="plain") == "x  a\ny  b"
