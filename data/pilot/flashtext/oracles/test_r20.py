from flashtext import KeywordProcessor


def test_an_empty_sentence_is_returned_unchanged():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert kp.replace_keywords("") == ""


def test_none_is_returned_unchanged():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert kp.replace_keywords(None) is None
