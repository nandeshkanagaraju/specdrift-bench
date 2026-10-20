"""R11: the fee is 1% bounded to [0.10, 5.00]; no amount travels free."""

from decimal import Decimal as D

from wallet import WalletService


def test_large_transfers_still_pay_the_fee():
    svc = WalletService()
    svc.open_account("a", "Ada", D("5000.00"))
    svc.open_account("b", "Bo", D("0.00"))

    assert svc.transfer("a", "b", D("900.00"), 1) == D("5.00")   # 1% = 9.00, capped at 5.00
