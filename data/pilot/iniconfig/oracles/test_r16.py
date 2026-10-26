from operator import attrgetter
from iniconfig import IniConfig


def test_sections_come_back_in_file_order():
    ini = IniConfig("p.ini", data="[zeta]\n[alpha]\n[mid]\n")
    names = list(map(attrgetter("name"), ini))
    assert names == ["zeta", "alpha", "mid"]


def test_the_first_section_in_the_file_comes_first():
    ini = IniConfig("p.ini", data="[b]\n[a]\n")
    assert next(iter(ini)).name == "b"
