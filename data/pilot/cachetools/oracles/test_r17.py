from cachetools.keys import hashkey, methodkey, typedkey


def test_position_differs_from_keyword():
    assert (hashkey(1) == hashkey(a=1)) is False
    assert (hashkey(1, 2) == hashkey(1, 2)) is True
