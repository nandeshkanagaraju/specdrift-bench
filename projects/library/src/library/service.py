"""The library service. Each check carries the id of the rule it implements."""

from __future__ import annotations

from decimal import Decimal

from library.errors import (
    BookUnavailable,
    DuplicateBook,
    DuplicateMember,
    LoanLimitExceeded,
    MemberSuspended,
    UnderageMember,
    UnknownEntity,
)
from library.fees import late_fee
from library.models import AuditEntry, Book, Loan, Member

MINIMUM_AGE = 18          # R01
MAX_ACTIVE_LOANS = 3      # R06
LOAN_PERIOD_DAYS = 14     # R12


class LibraryService:
    def __init__(self) -> None:
        self.members: dict[str, Member] = {}
        self.books: dict[str, Book] = {}
        self.loans: list[Loan] = []
        self.audit: list[AuditEntry] = []

    # ---------------------------------------------------------------- members

    def register_member(self, member_id: str, name: str, email: str, age: int) -> Member:
        """Register a member. Enforces R01, R02 and R03."""
        # R01/R02 - minimum age at registration.
        if age < MINIMUM_AGE:
            raise UnderageMember(f"{name} is {age}, minimum age is {MINIMUM_AGE}")

        # R03 - the email must not already belong to a member.
        if any(existing.email == email for existing in self.members.values()):
            raise DuplicateMember(f"{email} is already registered")

        member = Member(id=member_id, name=name, email=email, age=age)
        self.members[member_id] = member
        return member

    def suspend(self, member_id: str) -> None:
        self._member(member_id).suspended = True

    # -------------------------------------------------------------- catalogue

    def add_book(self, isbn: str, title: str, copies: int) -> Book:
        """Add a book to the catalogue. Enforces R04 and R05."""
        # R04/R05 - the ISBN must be unique across the catalogue.
        if isbn in self.books:
            raise DuplicateBook(f"ISBN {isbn} is already in the catalogue")

        book = Book(isbn=isbn, title=title, copies=copies)
        self.books[isbn] = book
        return book

    # ------------------------------------------------------------------ loans

    def active_loans(self, member_id: str) -> list[Loan]:
        return [loan for loan in self.loans if loan.member_id == member_id and loan.active]

    def borrow(self, member_id: str, isbn: str, day: int) -> Loan:
        """Borrow a book. Enforces R06 to R12."""
        member = self._member(member_id)
        book = self._book(isbn)

        # R09 - a suspended member may not borrow.
        if member.suspended:
            raise MemberSuspended(f"member {member_id} is suspended")

        # R06/R07 - at most 3 active loans at once.
        if len(self.active_loans(member_id)) >= MAX_ACTIVE_LOANS:
            raise LoanLimitExceeded(
                f"member {member_id} already holds {MAX_ACTIVE_LOANS} active loans"
            )

        # R08 - the book must have an available copy.
        if book.available <= 0:
            raise BookUnavailable(f"no copies of {isbn} are available")

        # R10 - decrement only now that every check above has passed.
        book.available -= 1

        # R12 - the loan runs for 14 days from the borrow date.
        loan = Loan(
            member_id=member_id,
            isbn=isbn,
            borrowed_on=day,
            due_on=day + LOAN_PERIOD_DAYS,
        )
        self.loans.append(loan)

        # R11 - the audit entry is appended after the loan has been recorded.
        self.audit.append(AuditEntry(action="borrow", member_id=member_id, isbn=isbn, day=day))
        return loan

    def return_book(self, member_id: str, isbn: str, day: int) -> Decimal:
        """Return a book and charge the late fee from R13."""
        for loan in self.loans:
            if loan.member_id == member_id and loan.isbn == isbn and loan.active:
                loan.returned_on = day
                self._book(isbn).available += 1
                self.audit.append(
                    AuditEntry(action="return", member_id=member_id, isbn=isbn, day=day)
                )
                # R13 - fee is charged per day past the due date.
                return late_fee(day - loan.due_on)

        raise UnknownEntity(f"no active loan of {isbn} for member {member_id}")

    def list_loans(self, member_id: str) -> list[Loan]:
        """R14 - active loans sorted by due date, earliest first."""
        return sorted(self.active_loans(member_id), key=lambda loan: loan.due_on)

    # --------------------------------------------------------------- internal

    def _member(self, member_id: str) -> Member:
        if member_id not in self.members:
            raise UnknownEntity(f"unknown member {member_id}")
        return self.members[member_id]

    def _book(self, isbn: str) -> Book:
        if isbn not in self.books:
            raise UnknownEntity(f"unknown book {isbn}")
        return self.books[isbn]
