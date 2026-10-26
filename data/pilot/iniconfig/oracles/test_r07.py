from iniconfig import IniConfig


def test_hash_comments_are_stripped_from_values_by_default():
    ini = IniConfig.parse("p.ini", data="[s]\nk=v # c\n")
    assert ini["s"]["k"] == "v"


def test_semicolon_comments_are_stripped_from_values_by_default():
    ini = IniConfig.parse("p.ini", data="[s]\nk=v ; c\n")
    assert ini["s"]["k"] == "v"
