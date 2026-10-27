from flashtext import KeywordProcessor


def test_spans_are_returned_with_the_clean_names():
    kp = KeywordProcessor()
    kp.add_keyword("Big Apple", "New York")
    kp.add_keyword("Bay Area")
    assert kp.extract_keywords("I love big Apple and Bay Area.", span_info=True) == [("New York", 7, 16), ("Bay Area", 21, 29)]


def test_a_keyword_at_the_start_of_a_sentence_has_a_zero_start():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert kp.extract_keywords("big apple.", span_info=True) == [("big apple", 0, 9)]
