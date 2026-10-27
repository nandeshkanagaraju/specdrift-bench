from colorama.winterm import WinTerm


def test_foreground_is_the_low_three_bits():
    term = WinTerm.__new__(WinTerm)
    term.set_attrs(0x07)
    assert term._fore == 7


def test_foreground_ignores_the_higher_bits():
    term = WinTerm.__new__(WinTerm)
    term.set_attrs(0xFD)
    assert term._fore == 5
