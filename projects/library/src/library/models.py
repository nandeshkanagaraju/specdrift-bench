"""Plain in-memory records. No database, no framework."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Member:
    id: str
    name: str
    email: str
    age: int
    suspended: bool = False


@dataclass
class Book:
    isbn: str
    title: str
    copies: int
    available: int = 0

    def __post_init__(self) -> None:
        if self.available == 0:
            self.available = self.copies


@dataclass
class Loan:
    member_id: str
    isbn: str
    borrowed_on: int      # day number, keeps the arithmetic obvious
    due_on: int
    returned_on: int | None = None

    @property
    def active(self) -> bool:
        return self.returned_on is None


@dataclass
class AuditEntry:
    action: str
    member_id: str
    isbn: str
    day: int


@dataclass
class Catalogue:
    books: dict[str, Book] = field(default_factory=dict)
