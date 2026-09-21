"""The wallet service. Each check carries the id of the rule it implements."""

from __future__ import annotations

from decimal import Decimal

from wallet.errors import (
    AccountFrozen,
    DailyLimitExceeded,
    DuplicateAccount,
    InsufficientFunds,
    InvalidAmount,
    UnknownAccount,
)
from wallet.fees import transfer_fee
from wallet.models import Account, AuditEntry, DailyTotals

DAILY_SEND_LIMIT = Decimal("1000.00")   # R07
ZERO = Decimal("0.00")


class WalletService:
    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self.audit: list[AuditEntry] = []
        self.daily = DailyTotals()
        self._seq = 0

    # --------------------------------------------------------------- accounts

    def open_account(self, account_id: str, owner: str, balance: Decimal) -> Account:
        """Open an account. Enforces R01, R02 and R03."""
        # R01/R02 - the opening balance may not be negative.
        if balance < ZERO:
            raise InvalidAmount(f"opening balance {balance} is negative")

        # R03 - the account id must be unused.
        if account_id in self.accounts:
            raise DuplicateAccount(f"account {account_id} already exists")

        account = Account(id=account_id, owner=owner, balance=balance)
        self.accounts[account_id] = account
        return account

    def freeze(self, account_id: str) -> None:
        self._account(account_id).frozen = True

    # -------------------------------------------------------------- transfers

    def transfer(self, sender_id: str, recipient_id: str, amount: Decimal, day: int) -> Decimal:
        """Move money between accounts. Enforces R04 to R12. Returns the fee charged."""
        sender = self._account(sender_id)
        recipient = self._account(recipient_id)

        # R04/R05 - the amount must be strictly positive.
        if amount <= ZERO:
            raise InvalidAmount(f"transfer amount {amount} must be greater than 0")

        # R09 - a frozen account may not send.
        if sender.frozen:
            raise AccountFrozen(f"account {sender_id} is frozen")

        fee = transfer_fee(amount)

        # R06 - the balance must cover the amount plus the fee.
        if sender.balance < amount + fee:
            raise InsufficientFunds(
                f"account {sender_id} holds {sender.balance}, needs {amount + fee}"
            )

        # R07/R08 - the daily total of sent amounts may not exceed the limit.
        if self.daily.total(sender_id, day) + amount > DAILY_SEND_LIMIT:
            raise DailyLimitExceeded(
                f"account {sender_id} would exceed the {DAILY_SEND_LIMIT} daily limit"
            )

        # R10 - debit only now that every check above has passed.
        sender.balance -= amount + fee
        recipient.balance += amount
        self.daily.add(sender_id, day, amount)

        # R12 - the audit entry is appended after both balances have been updated.
        self._record("transfer", sender_id, recipient_id, amount, fee, day)
        return fee

    def deposit(self, account_id: str, amount: Decimal, day: int) -> Decimal:
        """Add money to an account. Enforces R04/R05 on the amount."""
        account = self._account(account_id)
        if amount <= ZERO:
            raise InvalidAmount(f"deposit amount {amount} must be greater than 0")

        account.balance += amount
        self._record("deposit", account_id, "", amount, ZERO, day)
        return account.balance

    def statement(self, account_id: str) -> list[AuditEntry]:
        """R13 - the account's audit entries, newest first."""
        entries = [
            entry
            for entry in self.audit
            if entry.account_id == account_id or entry.counterparty == account_id
        ]
        return sorted(entries, key=lambda entry: entry.seq, reverse=True)

    # --------------------------------------------------------------- internal

    def _record(
        self,
        action: str,
        account_id: str,
        counterparty: str,
        amount: Decimal,
        fee: Decimal,
        day: int,
    ) -> None:
        self._seq += 1
        self.audit.append(
            AuditEntry(
                action=action,
                account_id=account_id,
                counterparty=counterparty,
                amount=amount,
                fee=fee,
                day=day,
                seq=self._seq,
            )
        )

    def _account(self, account_id: str) -> Account:
        if account_id not in self.accounts:
            raise UnknownAccount(f"unknown account {account_id}")
        return self.accounts[account_id]
