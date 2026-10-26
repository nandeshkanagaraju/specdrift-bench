from colorama.ansi import set_title


def test_set_title_wraps_the_title_between_osc_and_bell():
    assert set_title("hi") == "\x1b]2;hi\x07"


def test_set_title_with_an_empty_title():
    assert set_title("") == "\x1b]2;\x07"
