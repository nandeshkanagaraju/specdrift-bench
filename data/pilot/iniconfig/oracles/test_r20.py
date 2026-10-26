from iniconfig._parse import _parseline


def test_a_second_equals_sign_stays_in_the_value():
    assert _parseline("p", "k=a=b\n", 0, True, False) == ("k", "a=b")


def test_an_equals_sign_after_a_colon_separator_stays_in_the_value():
    assert _parseline("p", "k:a=b\n", 0, True, False) == ("k", "a=b")
