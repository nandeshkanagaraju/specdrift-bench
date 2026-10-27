from iniconfig import IniConfig


def test_a_missing_name_gives_the_default():
    ini = IniConfig("p.ini", data="[s]\nk=v\n")
    assert ini.get("s", "missing", "dflt") == "dflt"


def test_a_missing_section_gives_the_default():
    ini = IniConfig("p.ini", data="[s]\nk=v\n")
    assert ini.get("nosec", "k", "dflt") == "dflt"


def test_no_default_given_gives_none():
    ini = IniConfig("p.ini", data="[s]\nk=v\n")
    assert ini.get("s", "missing") is None


def test_an_existing_name_does_not_give_the_default():
    ini = IniConfig("p.ini", data="[s]\nk=v\n")
    assert ini.get("s", "k", "dflt") == "v"
