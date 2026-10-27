from flashtext import KeywordProcessor


def test_keywords_are_replaced_by_their_clean_names():
    kp = KeywordProcessor()
    kp.add_keyword("Big Apple", "New York")
    kp.add_keyword("Bay Area")
    assert kp.replace_keywords("I love Big Apple and bay area.") == "I love New York and Bay Area."


def test_a_sentence_without_keywords_is_unchanged():
    assert KeywordProcessor().replace_keywords("I love it.") == "I love it."
