from iniconfig import IniConfig


def test_names_come_back_in_file_order():
    ini = IniConfig("p.ini", data="[s]\nzz=1\naa=2\nmm=3\n")
    names = list(ini["s"])
    assert names == ["zz", "aa", "mm"]


def test_the_first_name_in_the_file_comes_first():
    ini = IniConfig("p.ini", data="[s]\nb=1\na=2\n")
    assert next(iter(ini["s"])) == "b"
