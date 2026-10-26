from shop import discount


def test_discount_is_ten_percent_from_one_hundred():
    assert discount(100) == 10.0
    assert discount(200) == 20.0
    assert discount(99) == 0
