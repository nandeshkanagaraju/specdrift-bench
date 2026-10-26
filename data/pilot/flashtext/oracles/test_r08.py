from flashtext import KeywordProcessor


def test_a_keyword_maps_to_its_clean_name():
    kp = KeywordProcessor()
    kp.add_keyword("j2ee", "Java")
    assert kp.get_keyword("j2ee") == "Java"


def test_item_access_maps_to_the_clean_name():
    kp = KeywordProcessor()
    kp.add_keyword("j2ee", "Java")
    assert kp["j2ee"] == "Java"


def test_an_unknown_keyword_maps_to_none():
    kp = KeywordProcessor()
    kp.add_keyword("j2ee", "Java")
    assert kp.get_keyword("nothing") is None
