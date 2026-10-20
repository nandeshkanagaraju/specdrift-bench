"""R11: the decision log MUST record the real token count, not a rounded one."""

from ratelimiter import RateLimiter


def test_logged_token_count_is_exact():
    rl = RateLimiter()
    rl.allow("a", 0.0)
    rl.allow("a", 0.25)                             # leaves a fractional count: 8.5
    assert rl.log[-1].tokens_left == rl.buckets["a"].tokens
