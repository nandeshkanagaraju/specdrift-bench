class AuthError(Exception):
    pass


class WeakPassword(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class UnknownUser(AuthError):
    pass


class AccountLocked(AuthError):
    pass


class SessionExpired(AuthError):
    pass


class Forbidden(AuthError):
    pass
