from tabulate import tabulate


def test_floatfmt_is_applied():
    assert tabulate([[3.14159]], floatfmt=".2f", tablefmt="plain") == "3.14"


def test_default_floatfmt_is_g():
    assert tabulate([[3.14159]], tablefmt="plain") == "3.14159"


def test_floatfmt_can_add_trailing_zeros():
    assert tabulate([[2.0]], floatfmt=".1f", tablefmt="plain") == "2.0"
