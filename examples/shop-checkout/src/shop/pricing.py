from decimal import ROUND_HALF_UP, Decimal

TAX_RATE = Decimal("0.08")
DISCOUNT_THRESHOLD = Decimal("100.00")
DISCOUNT_RATE = Decimal("0.10")
FREE_SHIPPING_THRESHOLD = Decimal("60.00")
SHIPPING_FEE = Decimal("6.99")
COUPONS = {"SAVE5": Decimal("5.00")}


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def subtotal(lines: list[tuple[Decimal, int]]) -> Decimal:
    return sum((price * qty for price, qty in lines), Decimal("0"))


def apply_discount(amount: Decimal) -> Decimal:
    if amount > DISCOUNT_THRESHOLD:
        return money(amount * (1 - DISCOUNT_RATE))
    return amount


def apply_coupon(amount: Decimal, code: str | None) -> Decimal:
    off = COUPONS.get(code or "", Decimal("0"))
    return max(amount - off, Decimal("0"))


def tax(amount: Decimal) -> Decimal:
    return money(amount * TAX_RATE)


def shipping(amount: Decimal) -> Decimal:
    return Decimal("0.00") if amount >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
