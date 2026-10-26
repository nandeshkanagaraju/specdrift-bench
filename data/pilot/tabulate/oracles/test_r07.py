from tabulate import tabulate


def test_a_column_of_numeric_strings_is_right_aligned():
    assert tabulate([["1"], ["22"]], tablefmt="plain") == " 1\n22"


def test_a_column_of_numeric_strings_takes_the_integer_format():
    assert tabulate([["5"]], intfmt="03d", tablefmt="plain") == "5"


def test_a_column_of_integers_is_right_aligned():
    assert tabulate([[1], [22]], tablefmt="plain") == " 1\n22"
