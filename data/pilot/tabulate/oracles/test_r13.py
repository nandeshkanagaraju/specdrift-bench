from tabulate import tabulate


def test_showindex_always_adds_an_index_column():
    assert tabulate([["a"], ["b"]], showindex="always", tablefmt="plain") == "0  a\n1  b"


def test_no_index_column_by_default():
    assert tabulate([["a"], ["b"]], tablefmt="plain") == "a\nb"


def test_showindex_never_adds_no_index_column():
    assert tabulate([["a"], ["b"]], showindex="never", tablefmt="plain") == "a\nb"


def test_a_sequence_gives_the_index_values():
    assert tabulate([["a"], ["b"]], showindex=["x", "y"], tablefmt="plain") == "x  a\ny  b"
