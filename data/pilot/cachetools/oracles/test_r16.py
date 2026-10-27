from cachetools.keys import hashkey, methodkey, typedkey


def test_keyword_order_is_irrelevant():
    assert (hashkey(a=1, b=2) == hashkey(b=2, a=1)) is True
    assert (hashkey(a=1, b=2) == hashkey(a=1, b=3)) is False
