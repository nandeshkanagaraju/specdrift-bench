from iniconfig import IniConfig


def test_section_names_keep_their_whitespace_by_default():
    ini = IniConfig.parse("p.ini", data="[ s ]\nk=v\n")
    assert (" s " in ini) is True
    assert ("s" in ini) is False


def test_section_names_are_stripped_when_asked():
    ini = IniConfig.parse("p.ini", data="[ s ]\nk=v\n", strip_section_whitespace=True)
    assert ("s" in ini) is True
