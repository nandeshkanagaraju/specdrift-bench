"""One test per rule, plus a boundary test for every numeric rule."""

from decimal import Decimal

import pytest
from wallet import (
    AccountFrozen,
    DailyLimitExceeded,
    DuplicateAccount,
    InsufficientFunds,
    InvalidAmount,
    WalletService,
    transfer_fee,
)

D = Decimal


@pytest.fixture()
def svc() -> WalletService:
    service = WalletService()
    service.open_account("a", "Ada", D("5000.00"))
    service.open_account("b", "Bo", D("10.00"))
    return service


# R01 / R02 --------------------------------------------------------------------

def test_r01_zero_opening_balance_is_allowed():
    service = WalletService()
    assert service.open_account("z", "Zed", D("0.00")).balance == D("0.00")


def test_r02_negative_opening_balance_raises():
    service = WalletService()
    with pytest.raises(InvalidAmount):
        service.open_account("n", "Neg", D("-0.01"))


# R03 --------------------------------------------------------------------------

def test_r03_duplicate_account_id_raises(svc):
    with pytest.raises(DuplicateAccount):
        svc.open_account("a", "Ada again", D("1.00"))


# R04 / R05 --------------------------------------------------------------------

def test_r04_smallest_positive_amount_is_allowed(svc):
    svc.transfer("a", "b", D("0.01"), day=1)
    assert svc.accounts["b"].balance == D("10.01")


def test_r05_zero_amount_raises(svc):
    with pytest.raises(InvalidAmount):
        svc.transfer("a", "b", D("0.00"), day=1)


def test_r05_negative_amount_raises(svc):
    with pytest.raises(InvalidAmount):
        svc.transfer("a", "b", D("-5.00"), day=1)


# R06 --------------------------------------------------------------------------

def test_r06_balance_must_cover_amount_plus_fee(svc):
    # b holds 10.00; 10.00 + a 0.10 fee is more than the balance.
    with pytest.raises(InsufficientFunds):
        svc.transfer("b", "a", D("10.00"), day=1)


def test_r06_exact_cover_is_allowed(svc):
    svc.transfer("b", "a", D("9.90"), day=1)
    assert svc.accounts["b"].balance == D("0.00")


# R07 / R08 --------------------------------------------------------------------

def test_r07_daily_limit_boundary_is_allowed(svc):
    svc.transfer("a", "b", D("1000.00"), day=1)
    assert svc.daily.total("a", 1) == D("1000.00")


def test_r08_exceeding_the_daily_limit_raises(svc):
    svc.transfer("a", "b", D("900.00"), day=1)
    with pytest.raises(DailyLimitExceeded):
        svc.transfer("a", "b", D("100.01"), day=1)


def test_r07_limit_resets_the_next_day(svc):
    svc.transfer("a", "b", D("1000.00"), day=1)
    svc.transfer("a", "b", D("1000.00"), day=2)
    assert svc.daily.total("a", 2) == D("1000.00")


# R09 --------------------------------------------------------------------------

def test_r09_frozen_account_cannot_send(svc):
    svc.freeze("a")
    with pytest.raises(AccountFrozen):
        svc.transfer("a", "b", D("1.00"), day=1)


def test_r09_frozen_account_can_still_receive(svc):
    svc.freeze("b")
    svc.transfer("a", "b", D("1.00"), day=1)
    assert svc.accounts["b"].balance == D("11.00")


# R10 --------------------------------------------------------------------------

def test_r10_failed_transfer_leaves_balances_untouched(svc):
    before = svc.accounts["a"].balance
    with pytest.raises(DailyLimitExceeded):
        svc.transfer("a", "b", D("1000.01"), day=1)
    assert svc.accounts["a"].balance == before
    assert svc.accounts["b"].balance == D("10.00")


# R11 --------------------------------------------------------------------------

def test_r11_one_percent_fee():
    assert transfer_fee(D("200.00")) == D("2.00")


def test_r11_minimum_fee_floor():
    assert transfer_fee(D("1.00")) == D("0.10")


def test_r11_maximum_fee_cap_boundary():
    assert transfer_fee(D("500.00")) == D("5.00")
    assert transfer_fee(D("900.00")) == D("5.00")


def test_r11_transfer_returns_the_fee(svc):
    assert svc.transfer("a", "b", D("200.00"), day=1) == D("2.00")


# R12 --------------------------------------------------------------------------

def test_r12_audit_entry_follows_the_balance_update(svc):
    svc.transfer("a", "b", D("50.00"), day=4)
    entry = svc.audit[-1]
    assert entry.action == "transfer"
    assert svc.accounts["b"].balance == D("60.00")
    assert entry.amount == D("50.00")


def test_r12_no_audit_entry_when_transfer_fails(svc):
    with pytest.raises(AccountFrozen):
        svc.freeze("a")
        svc.transfer("a", "b", D("1.00"), day=1)
    assert svc.audit == []


# R13 --------------------------------------------------------------------------

def test_r13_statement_is_newest_first(svc):
    svc.transfer("a", "b", D("1.00"), day=1)
    svc.transfer("a", "b", D("2.00"), day=2)
    svc.transfer("a", "b", D("3.00"), day=3)
    amounts = [entry.amount for entry in svc.statement("a")]
    assert amounts == [D("3.00"), D("2.00"), D("1.00")]
