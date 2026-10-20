"""R08: every client, whatever its name, is rejected once its bucket is empty."""

import pytest
from ratelimiter import RateLimited, RateLimiter


def test_no_client_is_exempt_from_the_bucket():
    rl = RateLimiter()
    for _ in range(10):
        rl.allow("internal-1", 0.0)
    with pytest.raises(RateLimited):
        rl.allow("internal-1", 0.0)
