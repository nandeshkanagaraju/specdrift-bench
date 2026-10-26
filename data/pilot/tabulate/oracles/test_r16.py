from tabulate import SEPARATING_LINE, tabulate


def test_a_separating_line_becomes_a_blank_line_in_the_plain_format():
    assert tabulate([["a", 1], SEPARATING_LINE, ["b", 2]], tablefmt="plain") == "a  1\n\nb  2"


def test_without_a_separating_line_the_rows_are_adjacent():
    assert tabulate([["a", 1], ["b", 2]], tablefmt="plain") == "a  1\nb  2"
