import pytest
from tabulate import tabulate


def test_a_number_is_not_tabular_data():
    with pytest.raises(TypeError):
        tabulate(5)


def test_a_dict_of_non_iterables_is_not_tabular_data():
    with pytest.raises(TypeError):
        tabulate({"a": 1})


def test_a_list_of_lists_is_accepted():
    assert tabulate([[1]], tablefmt="plain") == "1"
