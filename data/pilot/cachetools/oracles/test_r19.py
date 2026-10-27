from cachetools.keys import hashkey, methodkey, typedkey


def test_self_is_ignored():
    assert (methodkey("a", 1) == methodkey("b", 1)) is True
    assert (methodkey("a", 1) == methodkey("a", 2)) is False
