from flashtext import KeywordProcessor


def test_all_keywords_map_to_their_clean_names():
    kp = KeywordProcessor()
    kp.add_keyword("j2ee", "Java")
    kp.add_keyword("Python", "Python")
    assert kp.get_all_keywords() == {"j2ee": "Java", "python": "Python"}


def test_an_empty_processor_has_no_keywords():
    assert KeywordProcessor().get_all_keywords() == {}
