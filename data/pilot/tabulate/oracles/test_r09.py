from tabulate import tabulate


def test_the_keys_of_a_dict_are_the_headers():
    assert tabulate({"a": [1, 2], "b": [3, 4]}, headers="keys", tablefmt="plain") == "  a    b\n  1    3\n  2    4"


def test_a_dict_has_no_header_row_without_headers_keys():
    assert tabulate({"a": [1, 2], "b": [3, 4]}, tablefmt="plain") == "1  3\n2  4"
