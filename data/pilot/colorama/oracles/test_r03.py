from colorama import Style


def test_reset_all_is_escape_0():
    assert Style.RESET_ALL == "\x1b[0m"


def test_bright_is_a_different_code():
    assert Style.BRIGHT == "\x1b[1m"
