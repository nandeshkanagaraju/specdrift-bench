"""The spec authorises no operation beyond these; an extra public method is scope creep."""

from ratelimiter import RateLimiter

SPECIFIED = {"bucket_for", "allow", "block", "report"}


def test_limiter_exposes_no_unspecified_operation():
    public = {n for n in dir(RateLimiter) if not n.startswith("_") and callable(getattr(RateLimiter, n))}
    assert public - SPECIFIED == set()
