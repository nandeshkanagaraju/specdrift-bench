from flashtext import KeywordProcessor


def test_removing_a_present_keyword_returns_true():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    assert kp.remove_keyword("big apple") is True


def test_removing_it_again_returns_false():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    kp.remove_keyword("big apple")
    assert kp.remove_keyword("big apple") is False


def test_removing_an_unknown_keyword_returns_false():
    assert KeywordProcessor().remove_keyword("nope") is False


def test_a_removed_keyword_is_no_longer_contained():
    kp = KeywordProcessor()
    kp.add_keyword("big apple")
    kp.remove_keyword("big apple")
    assert ("big apple" in kp) is False
