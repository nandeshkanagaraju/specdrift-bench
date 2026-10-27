import pytest
from iniconfig import IniConfig


def test_an_unknown_section_raises_key_error():
    ini = IniConfig("p.ini", data="[s]\nk=v\n")
    with pytest.raises(KeyError):
        ini["nosec"]


def test_a_known_section_is_returned():
    ini = IniConfig("p.ini", data="[s]\nk=v\n")
    assert ini["s"].name == "s"
