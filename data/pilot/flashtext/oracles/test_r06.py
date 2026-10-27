from flashtext import KeywordProcessor


def test_two_distinct_keywords_count_as_two():
    kp = KeywordProcessor()
    kp.add_keyword("a")
    kp.add_keyword("b")
    assert len(kp) == 2


def test_the_same_keyword_added_twice_counts_once():
    kp = KeywordProcessor()
    kp.add_keyword("a")
    kp.add_keyword("a")
    assert len(kp) == 1


def test_the_same_keyword_in_another_case_counts_once():
    kp = KeywordProcessor()
    kp.add_keyword("Big")
    kp.add_keyword("big")
    assert len(kp) == 1
