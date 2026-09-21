"""Named failures the rate limiter raises. The spec names each one by class."""


class RateLimiterError(Exception):
    """Base class for every rate-limiter failure."""


class RateLimited(RateLimiterError):
    """R08 - the client's bucket is empty."""


class ClientBlocked(RateLimiterError):
    """R09 - the client is on the blocked list."""


class InvalidClock(RateLimiterError):
    """Time moved backwards, which the caller must not do."""
