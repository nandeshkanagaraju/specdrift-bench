from flashtext import KeywordProcessor


def test_clean_names_come_back_in_order():
    kp = KeywordProcessor()
    kp.add_keyword("Big Apple", "New York")
    kp.add_keyword("Bay Area")
    assert kp.extract_keywords("I love Big Apple and Bay Area.") == ["New York", "Bay Area"]


def test_a_keyword_without_a_clean_name_returns_itself():
    kp = KeywordProcessor()
    kp.add_keyword("Big Apple")
    assert kp.extract_keywords("I love big Apple and Bay Area.") == ["Big Apple"]
