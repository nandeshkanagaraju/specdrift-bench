from colorama import Back


def test_red_background_is_escape_41():
    assert Back.RED == "\x1b[41m"


def test_green_background_is_a_different_code():
    assert Back.GREEN == "\x1b[42m"
