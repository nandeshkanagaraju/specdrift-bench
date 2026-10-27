from cachetools.keys import hashkey, methodkey, typedkey


def test_types_are_part_of_the_key():
    assert (typedkey(1) == typedkey(1.0)) is False
    assert (typedkey(1) == typedkey(1)) is True
