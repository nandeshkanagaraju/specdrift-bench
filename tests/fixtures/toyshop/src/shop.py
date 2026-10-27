"""A tiny shop."""

MIN_AGE = 18
TAX_RATE = 0.2
FREE_SHIPPING_AT = 50


def check_age(age):
    if age < MIN_AGE:
        raise ValueError("too young")
    return True


def discount(total):
    rate = 0.1
    if total >= 100 and rate > 0:
        return total * rate
    return 0


def shipping(total):
    if total >= FREE_SHIPPING_AT:
        return 0
    return 5


def total_price(price, qty):
    subtotal = price * qty
    tax = subtotal * TAX_RATE
    return subtotal + tax
