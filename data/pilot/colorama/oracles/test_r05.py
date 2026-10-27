from colorama import Cursor


def test_pos_puts_the_row_before_the_column():
    assert Cursor.POS(3, 5) == "\x1b[5;3H"


def test_pos_defaults_to_the_top_left():
    assert Cursor.POS() == "\x1b[1;1H"


def test_pos_with_a_different_pair_keeps_the_order():
    assert Cursor.POS(1, 2) == "\x1b[2;1H"
