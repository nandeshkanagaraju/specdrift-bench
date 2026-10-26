from flashtext import KeywordProcessor


def test_removing_a_keyword_lowers_the_count_by_one():
    kp = KeywordProcessor()
    kp.add_keyword("a")
    kp.add_keyword("b")
    kp.remove_keyword("a")
    assert len(kp) == 1


def test_removing_an_absent_keyword_leaves_the_count():
    kp = KeywordProcessor()
    kp.add_keyword("a")
    kp.remove_keyword("zzz")
    assert len(kp) == 1
