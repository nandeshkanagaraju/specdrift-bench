"""R11: the fee MUST be rounded to 2 decimal places."""

from decimal import Decimal as D

from wallet import transfer_fee


def test_fee_has_exactly_two_decimal_places():
    assert transfer_fee(D("100.00")).as_tuple().exponent == -2
    assert str(transfer_fee(D("100.00"))) == "1.00"
