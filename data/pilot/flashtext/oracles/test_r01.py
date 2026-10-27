from flashtext import KeywordProcessor


def test_a_new_keyword_returns_true():
    kp = KeywordProcessor()
    assert kp.add_keyword("big apple") is True


def test_an_existing_keyword_returns_false():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert kp.add_keyword("big apple") is False


def test_an_existing_keyword_with_a_new_clean_name_returns_false():
    kp = KeywordProcessor()
    kp.add_keyword("a", "x")
    assert kp.add_keyword("a", "y") is False
