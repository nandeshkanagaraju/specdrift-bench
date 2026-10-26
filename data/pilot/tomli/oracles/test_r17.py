from tomli import loads


def test_a_z_suffix_gives_a_utc_offset_of_zero():
    assert loads("a = 1979-05-27T07:32:00Z")["a"].utcoffset().total_seconds() == 0


def test_a_date_time_without_a_suffix_has_no_time_zone():
    assert loads("a = 1979-05-27T07:32:00")["a"].tzinfo is None
