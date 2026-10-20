"""R11: the audit entry MUST be appended after the loan has been recorded."""

from library import LibraryService


def test_audit_is_appended_after_the_loan_is_recorded():
    svc = LibraryService()
    svc.register_member("m1", "Ada", "ada@example.com", 30)
    svc.add_book("isbn-1", "Book 1", copies=2)

    loans_when_audited = []

    class Spy(list):
        def append(self, item):
            loans_when_audited.append(len(svc.loans))
            super().append(item)

    svc.audit = Spy()
    svc.borrow("m1", "isbn-1", 1)

    assert loans_when_audited == [1]
