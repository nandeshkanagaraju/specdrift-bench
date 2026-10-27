from tabulate import tabulate


def test_a_scalar_maxcolwidths_wraps_the_column():
    assert tabulate([["aa bb cc"]], maxcolwidths=5, tablefmt="plain") == "aa bb\ncc"


def test_a_scalar_maxcolwidths_wraps_every_column():
    assert tabulate([["aa bb", "cc dd"]], maxcolwidths=2, tablefmt="plain") == "aa  cc\nbb  dd"


def test_no_maxcolwidths_leaves_the_text_on_one_line():
    assert tabulate([["aa bb cc"]], tablefmt="plain") == "aa bb cc"
