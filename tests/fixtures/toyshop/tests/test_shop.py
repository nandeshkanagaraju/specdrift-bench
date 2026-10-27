import pytest
from shop import check_age, discount, total_price


def test_adult():
    assert check_age(18) is True


def test_minor():
    with pytest.raises(ValueError):
        check_age(17)


def test_discount():
    assert discount(100) == 10.0
    assert discount(99) == 0


def test_total():
    assert total_price(10, 2) == 24.0
