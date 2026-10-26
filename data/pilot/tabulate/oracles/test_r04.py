from tabulate import tabulate


def test_none_is_replaced_by_missingval():
    assert tabulate([["a", None]], missingval="?", tablefmt="plain") == "a  ?"


def test_none_is_empty_by_default():
    assert tabulate([["a", None]], tablefmt="plain") == "a"
