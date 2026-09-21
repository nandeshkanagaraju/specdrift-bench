"""Named failures the wallet service raises. The spec names each one by class."""


class WalletError(Exception):
    """Base class for every wallet failure."""


class InvalidAmount(WalletError):
    """R02 / R05 - an amount outside the allowed range."""


class DuplicateAccount(WalletError):
    """R03 - the account id is already in use."""


class InsufficientFunds(WalletError):
    """R06 - the balance does not cover the amount plus the fee."""


class DailyLimitExceeded(WalletError):
    """R08 - the transfer would breach the daily sending limit."""


class AccountFrozen(WalletError):
    """R09 - a frozen account attempted to send money."""


class UnknownAccount(WalletError):
    """The account id is not known to the service."""
