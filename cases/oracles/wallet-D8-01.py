"""The spec authorises no operation beyond these; an extra public method is scope creep."""

from wallet import WalletService

SPECIFIED = {"open_account", "freeze", "transfer", "deposit", "statement"}


def test_service_exposes_no_unspecified_operation():
    public = {n for n in dir(WalletService) if not n.startswith("_") and callable(getattr(WalletService, n))}
    assert public - SPECIFIED == set()
