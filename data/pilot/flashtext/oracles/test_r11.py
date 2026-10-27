from flashtext import KeywordProcessor


def test_removing_a_longer_keyword_keeps_its_prefix_keyword():
    kp = KeywordProcessor()
    kp.add_keyword("big")
    kp.add_keyword("big apple")
    kp.remove_keyword("big apple")
    assert kp.get_all_keywords() == {"big": "big"}


def test_removing_the_shorter_keyword_keeps_the_longer_one():
    kp = KeywordProcessor()
    kp.add_keyword("big")
    kp.add_keyword("big apple")
    kp.remove_keyword("big")
    assert kp.get_all_keywords() == {"big apple": "big apple"}
