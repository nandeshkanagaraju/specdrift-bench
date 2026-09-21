"""Named failures the library service raises. The spec names each one by class."""


class LibraryError(Exception):
    """Base class for every library failure."""


class UnderageMember(LibraryError):
    """R02 - registration attempted below the minimum age."""


class DuplicateMember(LibraryError):
    """R03 - the email already belongs to a registered member."""


class DuplicateBook(LibraryError):
    """R05 - the ISBN is already in the catalogue."""


class LoanLimitExceeded(LibraryError):
    """R07 - the member already holds the maximum number of active loans."""


class BookUnavailable(LibraryError):
    """R08 - no copies of the book are available."""


class MemberSuspended(LibraryError):
    """R09 - a suspended member attempted to borrow."""


class UnknownEntity(LibraryError):
    """The member or book id is not known to the service."""
