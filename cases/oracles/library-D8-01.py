"""The spec authorises no operation beyond these; an extra public method is scope creep."""

from library import LibraryService

SPECIFIED = {
    "register_member", "suspend", "add_book", "active_loans",
    "borrow", "return_book", "list_loans",
}


def test_service_exposes_no_unspecified_operation():
    public = {n for n in dir(LibraryService) if not n.startswith("_") and callable(getattr(LibraryService, n))}
    assert public - SPECIFIED == set()
