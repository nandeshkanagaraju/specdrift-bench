"""R12: a client MUST be blocked automatically once it has accumulated 5 rejections."""

import pytest
from ratelimiter import RateLimited, RateLimiter


def test_five_rejections_block_the_client():
    rl = RateLimiter()
    for _ in range(10):
        rl.allow("c", 0.0)                          # spend the whole burst
    for _ in range(5):
        with pytest.raises(RateLimited):
            rl.allow("c", 0.0)

    assert "c" in rl.blocked
