from tomli import loads


def test_a_minus_offset_is_negative():
    assert loads("a = 1979-05-27T00:32:00-07:00")["a"].utcoffset().total_seconds() == -25200


def test_a_plus_offset_is_positive():
    assert loads("a = 1979-05-27T00:32:00+07:00")["a"].utcoffset().total_seconds() == 25200
