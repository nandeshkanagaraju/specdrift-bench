from tabulate import tabulate


def test_intfmt_is_applied():
    assert tabulate([[5]], intfmt="03d", tablefmt="plain") == "005"


def test_default_intfmt_leaves_the_integer_unchanged():
    assert tabulate([[5]], tablefmt="plain") == "5"
