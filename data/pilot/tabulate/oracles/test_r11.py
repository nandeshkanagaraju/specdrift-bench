from tabulate import tabulate


def test_a_missing_key_leaves_the_cell_empty():
    assert tabulate([{"a": 1}, {"a": 2, "b": 3}], headers="keys", tablefmt="plain") == "  a    b\n  1\n  2    3"


def test_columns_follow_the_order_in_which_keys_first_appear():
    assert tabulate([{"b": 1}, {"a": 2}], headers="keys", tablefmt="plain") == "  b    a\n  1\n       2"
