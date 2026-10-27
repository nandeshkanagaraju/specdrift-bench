from iniconfig import IniConfig


def test_len_is_applied_to_the_stored_value():
    ini = IniConfig("p.ini", data="[s]\nk=abc\n")
    assert ini.get("s", "k", None, len) == 3


def test_int_is_applied_to_the_stored_value():
    ini = IniConfig("p.ini", data="[s]\nk=42\n")
    assert ini.get("s", "k", None, int) == 42
