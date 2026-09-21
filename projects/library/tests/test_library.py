"""One test per rule, plus a boundary test for every numeric rule."""

from decimal import Decimal

import pytest
from library import (
    BookUnavailable,
    DuplicateBook,
    DuplicateMember,
    LibraryService,
    LoanLimitExceeded,
    MemberSuspended,
    UnderageMember,
    late_fee,
)


@pytest.fixture()
def svc() -> LibraryService:
    service = LibraryService()
    service.register_member("m1", "Ada", "ada@example.com", 30)
    for n in range(1, 6):
        service.add_book(f"isbn-{n}", f"Book {n}", copies=2)
    return service


# R01 / R02 --------------------------------------------------------------------

def test_r01_minimum_age_boundary_accepts_exactly_18():
    service = LibraryService()
    member = service.register_member("m9", "Bo", "bo@example.com", 18)
    assert member.age == 18


def test_r02_underage_registration_raises(svc):
    with pytest.raises(UnderageMember):
        svc.register_member("m10", "Kid", "kid@example.com", 17)


# R03 --------------------------------------------------------------------------

def test_r03_duplicate_email_raises(svc):
    with pytest.raises(DuplicateMember):
        svc.register_member("m11", "Other", "ada@example.com", 40)


# R04 / R05 --------------------------------------------------------------------

def test_r04_isbns_are_unique(svc):
    assert len(svc.books) == len({isbn for isbn in svc.books})


def test_r05_duplicate_isbn_raises(svc):
    with pytest.raises(DuplicateBook):
        svc.add_book("isbn-1", "Copy", copies=1)


# R06 / R07 --------------------------------------------------------------------

def test_r06_three_active_loans_are_allowed(svc):
    for n in range(1, 4):
        svc.borrow("m1", f"isbn-{n}", day=0)
    assert len(svc.active_loans("m1")) == 3


def test_r07_fourth_loan_raises(svc):
    for n in range(1, 4):
        svc.borrow("m1", f"isbn-{n}", day=0)
    with pytest.raises(LoanLimitExceeded):
        svc.borrow("m1", "isbn-4", day=0)


# R08 --------------------------------------------------------------------------

def test_r08_unavailable_book_raises(svc):
    svc.register_member("m2", "Bea", "bea@example.com", 22)
    svc.register_member("m3", "Cai", "cai@example.com", 23)
    svc.borrow("m1", "isbn-1", day=0)
    svc.borrow("m2", "isbn-1", day=0)
    with pytest.raises(BookUnavailable):
        svc.borrow("m3", "isbn-1", day=0)


# R09 --------------------------------------------------------------------------

def test_r09_suspended_member_cannot_borrow(svc):
    svc.suspend("m1")
    with pytest.raises(MemberSuspended):
        svc.borrow("m1", "isbn-1", day=0)


def test_r09_suspension_does_not_consume_a_copy(svc):
    svc.suspend("m1")
    with pytest.raises(MemberSuspended):
        svc.borrow("m1", "isbn-1", day=0)
    assert svc.books["isbn-1"].available == 2


# R10 --------------------------------------------------------------------------

def test_r10_failed_borrow_leaves_availability_untouched(svc):
    for n in range(1, 4):
        svc.borrow("m1", f"isbn-{n}", day=0)
    before = svc.books["isbn-4"].available
    with pytest.raises(LoanLimitExceeded):
        svc.borrow("m1", "isbn-4", day=0)
    assert svc.books["isbn-4"].available == before


# R11 --------------------------------------------------------------------------

def test_r11_audit_entry_follows_the_loan(svc):
    svc.borrow("m1", "isbn-1", day=3)
    assert len(svc.loans) == 1
    assert svc.audit[-1].action == "borrow"
    assert svc.audit[-1].day == 3


def test_r11_no_audit_entry_when_borrow_fails(svc):
    svc.suspend("m1")
    with pytest.raises(MemberSuspended):
        svc.borrow("m1", "isbn-1", day=0)
    assert svc.audit == []


# R12 --------------------------------------------------------------------------

def test_r12_loan_period_is_14_days(svc):
    loan = svc.borrow("m1", "isbn-1", day=10)
    assert loan.due_on == 24


# R13 --------------------------------------------------------------------------

def test_r13_daily_rate():
    assert late_fee(4) == Decimal("2.00")


def test_r13_cap_boundary():
    assert late_fee(40) == Decimal("20.00")
    assert late_fee(41) == Decimal("20.00")


def test_r13_not_late_is_free():
    assert late_fee(0) == Decimal("0.00")
    assert late_fee(-3) == Decimal("0.00")


def test_r13_return_charges_the_fee(svc):
    svc.borrow("m1", "isbn-1", day=0)
    assert svc.return_book("m1", "isbn-1", day=18) == Decimal("2.00")


# R14 --------------------------------------------------------------------------

def test_r14_loans_are_sorted_by_due_date(svc):
    svc.borrow("m1", "isbn-3", day=20)
    svc.borrow("m1", "isbn-1", day=0)
    svc.borrow("m1", "isbn-2", day=10)
    assert [loan.due_on for loan in svc.list_loans("m1")] == [14, 24, 34]
