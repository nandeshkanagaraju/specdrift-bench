from tabulate import tabulate


def test_the_first_row_becomes_the_header_and_leaves_the_data():
    assert tabulate([["n", "v"], ["a", 1], ["b", 2]], headers="firstrow", tablefmt="plain") == (
        "n      v\na      1\nb      2"
    )


def test_a_lone_first_row_gives_only_a_header():
    assert tabulate([["n", "v"]], headers="firstrow", tablefmt="plain") == "n    v"


def test_without_firstrow_the_first_row_is_data():
    assert tabulate([["n", "v"], ["a", 1]], tablefmt="plain") == "n  v\na  1"
