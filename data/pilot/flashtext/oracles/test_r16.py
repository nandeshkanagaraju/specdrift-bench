from flashtext import KeywordProcessor


def test_an_empty_sentence_gives_an_empty_list():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert kp.extract_keywords("") == []


def test_none_gives_an_empty_list():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert kp.extract_keywords(None) == []
