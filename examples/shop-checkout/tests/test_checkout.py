from decimal import Decimal

import pytest

from shop.checkout import Checkout, Line
from shop.errors import EmptyCart, InvalidQuantity, OutOfStock, PaymentDeclined
from shop.inventory import Inventory


def make(stock=None, charge=None):
    charges = []
    fn = charge or (lambda amount: charges.append(amount))
    return Checkout(Inventory(stock or {"A": 50, "B": 50}), fn), charges


def test_empty_cart():
    desk, _ = make()
    with pytest.raises(EmptyCart):
        desk.place_order("u", [])


def test_quantity_limits():
    desk, _ = make()
    with pytest.raises(InvalidQuantity):
        desk.place_order("u", [Line("A", Decimal("1"), 0)])
    with pytest.raises(InvalidQuantity):
        desk.place_order("u", [Line("A", Decimal("1"), 21)])


def test_small_order_pricing():
    desk, charges = make()
    order = desk.place_order("u", [Line("A", Decimal("10.00"), 2)])
    assert order.shipping == Decimal("6.99")
    assert order.tax == Decimal("1.60")
    assert charges == [Decimal("28.59")]


def test_discount_for_large_order():
    desk, _ = make()
    order = desk.place_order("u", [Line("A", Decimal("60.00"), 2)])
    assert order.total == Decimal("116.64")


def test_coupon_floor():
    desk, _ = make()
    order = desk.place_order("u", [Line("A", Decimal("2.00"), 1)], coupon="SAVE5")
    assert order.tax == Decimal("0.00")


def test_out_of_stock_does_not_charge():
    desk, charges = make({"A": 1})
    with pytest.raises(OutOfStock):
        desk.place_order("u", [Line("A", Decimal("5"), 2)])
    assert charges == []


def test_declined_payment_raises():
    def decline(amount):
        raise PaymentDeclined()

    desk, _ = make(charge=decline)
    with pytest.raises(PaymentDeclined):
        desk.place_order("u", [Line("A", Decimal("5"), 1)])


def test_order_ids_are_sequential():
    desk, _ = make()
    first = desk.place_order("u", [Line("A", Decimal("5"), 1)])
    second = desk.place_order("u", [Line("A", Decimal("5"), 1)])
    assert (first.id, second.id) == ("ORD-1000", "ORD-1001")
