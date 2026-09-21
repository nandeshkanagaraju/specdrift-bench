"""Plain in-memory records."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Account:
    id: str
    owner: str
    balance: Decimal
    frozen: bool = False


@dataclass
class AuditEntry:
    action: str
    account_id: str
    counterparty: str
    amount: Decimal
    fee: Decimal
    day: int
    seq: int = 0


@dataclass
class DailyTotals:
    """Amount already sent per (account, day)."""

    sent: dict[tuple[str, int], Decimal] = field(default_factory=dict)

    def total(self, account_id: str, day: int) -> Decimal:
        return self.sent.get((account_id, day), Decimal("0.00"))

    def add(self, account_id: str, day: int, amount: Decimal) -> None:
        key = (account_id, day)
        self.sent[key] = self.sent.get(key, Decimal("0.00")) + amount
