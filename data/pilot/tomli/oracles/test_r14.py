from tomli import loads


def test_hex_integers_use_base_16():
    assert loads("a = 0xff") == {"a": 255}


def test_octal_integers_use_base_8():
    assert loads("a = 0o17") == {"a": 15}


def test_binary_integers_use_base_2():
    assert loads("a = 0b101") == {"a": 5}


def test_decimal_integers_use_base_10():
    assert loads("a = 17") == {"a": 17}
