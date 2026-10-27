from iniconfig import IniConfig


def test_a_section_is_on_the_line_it_is_written_on_counted_from_one():
    ini = IniConfig("p.ini", data="[s]\nk=v\n")
    assert ini.lineof("s") == 1


def test_a_name_is_on_the_line_it_is_written_on_counted_from_one():
    ini = IniConfig("p.ini", data="[s]\nk=v\n")
    assert ini.lineof("s", "k") == 2
