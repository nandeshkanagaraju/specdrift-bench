from tabulate import tabulate


def test_decimal_points_line_up():
    assert tabulate([[1.5], [22.25]], tablefmt="plain") == " 1.5\n22.25"


def test_decimal_points_line_up_with_a_longer_fraction_first():
    assert tabulate([[1.25], [10.5]], tablefmt="plain") == " 1.25\n10.5"
