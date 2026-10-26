from shop import total_price


def test_total_includes_twenty_percent_tax():
    assert total_price(10, 2) == 24.0
    assert total_price(0, 5) == 0
