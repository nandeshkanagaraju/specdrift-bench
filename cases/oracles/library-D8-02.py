"""No rule suspends a member automatically; only an explicit suspend() does (R09)."""

from library import LibraryService


def test_a_large_late_fee_does_not_suspend_the_member():
    svc = LibraryService()
    svc.register_member("m1", "Ada", "ada@example.com", 30)
    svc.add_book("isbn-1", "Book 1", copies=1)
    svc.borrow("m1", "isbn-1", 1)

    fee = svc.return_book("m1", "isbn-1", 200)     # far past the 14-day period: capped fee

    assert fee > 10
    assert svc.members["m1"].suspended is False
