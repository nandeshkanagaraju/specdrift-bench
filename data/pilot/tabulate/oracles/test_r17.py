from tabulate import simple_separated_format, tabulate


def test_data_rows_use_the_separator():
    assert tabulate([["foo", 1], ["spam", 23]], tablefmt=simple_separated_format(",")) == "foo , 1\nspam,23"


def test_the_header_row_uses_the_separator():
    assert tabulate([["a", 1]], headers=["x", "y"], tablefmt=simple_separated_format("|")) == "x  |  y\na  |  1"
