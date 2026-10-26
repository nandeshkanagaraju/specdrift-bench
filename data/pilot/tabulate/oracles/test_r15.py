from tabulate import tabulate


def test_no_headers_and_no_rows_give_an_empty_string():
    assert tabulate([]) == ""


def test_a_single_row_gives_that_row():
    assert tabulate([["a"]], tablefmt="plain") == "a"
