from iniconfig import IniConfig


def test_the_constructor_keeps_a_hash_comment_in_the_value():
    ini = IniConfig("p.ini", data="[s]\nk=v # c\n")
    assert ini["s"]["k"] == "v # c"


def test_the_constructor_keeps_a_semicolon_comment_in_the_value():
    ini = IniConfig("p.ini", data="[s]\nk=v ; c\n")
    assert ini["s"]["k"] == "v ; c"
