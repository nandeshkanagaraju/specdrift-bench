from colorama.winterm import WinTerm


def test_background_is_read_from_bits_4_to_6():
    term = WinTerm.__new__(WinTerm)
    term.set_attrs(0x70)
    assert term._back == 7


def test_background_ignores_the_high_bit():
    term = WinTerm.__new__(WinTerm)
    term.set_attrs(0xF0)
    assert term._back == 7


def test_a_background_of_one():
    term = WinTerm.__new__(WinTerm)
    term.set_attrs(0x10)
    assert term._back == 1
