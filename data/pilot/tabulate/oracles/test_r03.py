from tabulate import tabulate


def test_colalign_overrides_the_alignment_of_a_column():
    assert tabulate([["ab", 1], ["c", 22]], tablefmt="plain", colalign=("right", "left")) == "ab  1\n c  22"


def test_global_in_colalign_keeps_the_default_for_that_column():
    assert tabulate([["ab", 1], ["c", 22]], tablefmt="plain", colalign=("global", "left")) == "ab  1\nc   22"


def test_without_colalign_the_defaults_apply():
    assert tabulate([["ab", 1], ["c", 22]], tablefmt="plain") == "ab   1\nc   22"
