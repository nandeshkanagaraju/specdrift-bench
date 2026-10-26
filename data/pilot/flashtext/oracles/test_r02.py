from flashtext import KeywordProcessor


def test_keywords_are_stored_in_lowercase_by_default():
    kp = KeywordProcessor()
    kp.add_keyword("Big Apple", "x")
    assert kp.get_all_keywords() == {"big apple": "x"}


def test_keywords_keep_their_case_when_case_sensitive():
    kp = KeywordProcessor(case_sensitive=True)
    kp.add_keyword("Big Apple", "x")
    assert kp.get_all_keywords() == {"Big Apple": "x"}
