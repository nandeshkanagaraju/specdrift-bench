from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from shop import pricing
from shop.errors import EmptyCart, InvalidQuantity, PaymentDeclined
from shop.inventory import Inventory


@dataclass
class Line:
    sku: str
    unit_price: Decimal
    quantity: int


@dataclass
class Order:
    id: str
    total: Decimal
    shipping: Decimal
    tax: Decimal


class Checkout:
    def __init__(self, inventory: Inventory, charge: Callable[[Decimal], None]) -> None:
        self.inventory = inventory
        self.charge = charge
        self.next_number = 1000
        self.loyalty: dict[str, int] = {}

    def place_order(self, customer: str, lines: list[Line], coupon: str | None = None) -> Order:
        if not lines:
            raise EmptyCart()
        for line in lines:
            if line.quantity < 1 or line.quantity > 20:
                raise InvalidQuantity(line.sku)

        amount = pricing.subtotal([(line.unit_price, line.quantity) for line in lines])
        amount = pricing.apply_discount(amount)
        amount = pricing.apply_coupon(amount, coupon)
        tax = pricing.tax(amount)
        shipping = pricing.shipping(amount)
        total = amount + tax + shipping

        items = {line.sku: line.quantity for line in lines}
        self.inventory.reserve(items)
        try:
            self.charge(total)
        except PaymentDeclined:
            raise

        self.loyalty[customer] = self.loyalty.get(customer, 0) + int(total)
        order = Order(f"ORD-{self.next_number}", total, shipping, tax)
        self.next_number += 1
        return order
