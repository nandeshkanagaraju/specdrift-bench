"""R05: a bucket MUST NOT hold more than the burst limit (10) after a refill."""

from ratelimiter import TokenBucket


def test_refill_never_leaves_more_than_ten_tokens():
    bucket = TokenBucket(client_id="a")             # starts full (R02)
    bucket.refill(0.3)                              # +0.6 tokens would overshoot the cap
    assert bucket.tokens <= 10.0
