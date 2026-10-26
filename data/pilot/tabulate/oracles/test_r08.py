from tabulate import tabulate


def test_disable_numparse_keeps_numeric_strings_left_aligned():
    assert tabulate([["1"], ["22"]], disable_numparse=True, tablefmt="plain") == "1\n22"


def test_disable_numparse_with_a_column_list_affects_only_those_columns():
    assert tabulate([["1", "2"], ["22", "33"]], disable_numparse=[0], tablefmt="plain") == "1    2\n22  33"
