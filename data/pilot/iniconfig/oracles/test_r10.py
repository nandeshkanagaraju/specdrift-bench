from iniconfig._parse import _parseline


def test_the_text_between_the_brackets_is_the_section_name():
    assert _parseline("p", "[ab]\n", 0, True, False) == ("ab", None)


def test_a_one_character_section_name_is_kept_whole():
    assert _parseline("p", "[x]\n", 0, True, False) == ("x", None)
