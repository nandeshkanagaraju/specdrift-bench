from colorama import Back, Fore


def test_foreground_reset_is_escape_39():
    assert Fore.RESET == "\x1b[39m"


def test_background_reset_is_a_different_code():
    assert Back.RESET == "\x1b[49m"
