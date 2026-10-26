from tabulate import tabulate


def test_numbers_are_right_aligned_and_text_left_aligned_by_default():
    assert tabulate([["ab", 1], ["c", 22]], tablefmt="plain") == "ab   1\nc   22"


def test_numalign_changes_only_the_numeric_column():
    assert tabulate([["ab", 1], ["c", 22]], tablefmt="plain", numalign="left") == "ab  1\nc   22"


def test_stralign_changes_only_the_text_column():
    assert tabulate([["ab", 1], ["c", 22]], tablefmt="plain", stralign="right") == "ab   1\n c  22"
