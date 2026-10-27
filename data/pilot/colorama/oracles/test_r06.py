from colorama.ansi import clear_screen


def test_clear_screen_defaults_to_the_whole_screen():
    assert clear_screen() == "\x1b[2J"


def test_clear_screen_accepts_another_mode():
    assert clear_screen(0) == "\x1b[0J"
