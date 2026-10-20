"""R12: the audit entry MUST be appended after both balances have been updated."""

from decimal import Decimal as D

from wallet import WalletService


def test_audit_is_recorded_after_both_balances_move():
    svc = WalletService()
    svc.open_account("a", "Ada", D("5000.00"))
    svc.open_account("b", "Bo", D("10.00"))

    balances_when_audited = []
    original = svc._record

    def spy(*args, **kwargs):
        balances_when_audited.append((svc.accounts["a"].balance, svc.accounts["b"].balance))
        return original(*args, **kwargs)

    svc._record = spy
    svc.transfer("a", "b", D("100.00"), 1)          # fee 1.00

    assert balances_when_audited == [(D("4899.00"), D("110.00"))]
