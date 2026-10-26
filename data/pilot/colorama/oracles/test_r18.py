from colorama.winterm import WinTerm


def test_attributes_combine_foreground_background_and_style():
    term = WinTerm.__new__(WinTerm)
    term._fore = 5
    term._back = 1
    term._style = 8
    term._light = 0
    assert term.get_attrs() == 29


def test_light_bits_are_or_ed_with_the_style():
    term = WinTerm.__new__(WinTerm)
    term._fore = 1
    term._back = 2
    term._style = 0
    term._light = 8
    assert term.get_attrs() == 41
