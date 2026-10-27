from flashtext import KeywordProcessor


def test_case_is_ignored_by_default():
    kp = KeywordProcessor()
    kp.add_keyword("Big Apple", "New York")
    assert kp.extract_keywords("I love BIG apple.") == ["New York"]


def test_case_matters_when_case_sensitive():
    kp = KeywordProcessor(case_sensitive=True)
    kp.add_keyword("Big Apple", "New York")
    kp.add_keyword("Bay Area")
    assert kp.extract_keywords("I love big Apple and Bay Area.") == ["Bay Area"]
