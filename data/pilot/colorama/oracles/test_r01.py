from colorama import Fore


def test_red_foreground_is_escape_31():
    assert Fore.RED == "\x1b[31m"


def test_green_foreground_is_a_different_code():
    assert Fore.GREEN == "\x1b[32m"
