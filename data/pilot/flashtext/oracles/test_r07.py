from flashtext import KeywordProcessor


def test_a_complete_keyword_is_contained():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert ("big apple" in kp) is True


def test_a_prefix_is_not_contained():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert ("big" in kp) is False


def test_a_keyword_plus_extra_text_is_not_contained():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert ("big apple pie" in kp) is False
