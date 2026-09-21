"""One test per rule, plus a boundary test for every numeric rule."""

import pytest
from ratelimiter import (
    BLOCK_AFTER_REJECTIONS,
    BURST_LIMIT,
    REFILL_PER_SECOND,
    ClientBlocked,
    RateLimited,
    RateLimiter,
    TokenBucket,
)


@pytest.fixture()
def rl() -> RateLimiter:
    return RateLimiter()


def drain(rl: RateLimiter, client: str, now: float = 0.0) -> None:
    """Spend every token in the client's bucket."""
    for _ in range(int(BURST_LIMIT)):
        rl.allow(client, now)


# R01 / R02 --------------------------------------------------------------------

def test_r01_each_client_gets_its_own_bucket(rl):
    rl.allow("a", 0.0)
    rl.allow("b", 0.0)
    assert set(rl.buckets) == {"a", "b"}
    assert rl.buckets["a"] is not rl.buckets["b"]


def test_r02_new_bucket_starts_full(rl):
    bucket = rl.bucket_for("fresh", 0.0)
    assert bucket.tokens == BURST_LIMIT


# R03 --------------------------------------------------------------------------

def test_r03_burst_limit_is_ten():
    assert BURST_LIMIT == 10.0


def test_r03_exactly_ten_requests_are_allowed(rl):
    for _ in range(10):
        rl.allow("a", 0.0)
    assert rl.stats["a"].allowed == 10


# R04 --------------------------------------------------------------------------

def test_r04_refill_rate_is_two_per_second():
    assert REFILL_PER_SECOND == 2.0


def test_r04_refill_adds_two_tokens_per_second():
    bucket = TokenBucket(client_id="a", tokens=0.0, updated_at=0.0)
    bucket.refill(3.0)
    assert bucket.tokens == 6.0


# R05 --------------------------------------------------------------------------

def test_r05_refill_never_exceeds_the_burst_limit():
    bucket = TokenBucket(client_id="a", tokens=0.0, updated_at=0.0)
    bucket.refill(100.0)
    assert bucket.tokens == BURST_LIMIT


# R06 / R07 --------------------------------------------------------------------

def test_r06_request_allowed_while_tokens_remain(rl):
    assert rl.allow("a", 0.0).allowed is True


def test_r07_allowed_request_consumes_exactly_one_token(rl):
    rl.allow("a", 0.0)
    assert rl.buckets["a"].tokens == BURST_LIMIT - 1.0


def test_r06_one_token_boundary_is_allowed(rl):
    rl.buckets["a"] = TokenBucket(client_id="a", tokens=1.0, updated_at=0.0)
    assert rl.allow("a", 0.0).allowed is True


# R08 --------------------------------------------------------------------------

def test_r08_empty_bucket_is_rejected(rl):
    drain(rl, "a")
    with pytest.raises(RateLimited):
        rl.allow("a", 0.0)


def test_r08_partial_token_is_rejected(rl):
    rl.buckets["a"] = TokenBucket(client_id="a", tokens=0.9, updated_at=0.0)
    with pytest.raises(RateLimited):
        rl.allow("a", 0.0)


# R09 --------------------------------------------------------------------------

def test_r09_blocked_client_is_rejected_even_with_a_full_bucket(rl):
    rl.allow("a", 0.0)
    rl.block("a")
    with pytest.raises(ClientBlocked):
        rl.allow("a", 0.0)


# R10 --------------------------------------------------------------------------

def test_r10_rejected_request_does_not_consume_a_token(rl):
    rl.buckets["a"] = TokenBucket(client_id="a", tokens=0.5, updated_at=0.0)
    with pytest.raises(RateLimited):
        rl.allow("a", 0.0)
    assert rl.buckets["a"].tokens == 0.5


# R11 --------------------------------------------------------------------------

def test_r11_decision_logged_after_the_token_update(rl):
    rl.allow("a", 0.0)
    entry = rl.log[-1]
    assert entry.allowed is True
    assert entry.tokens_left == rl.buckets["a"].tokens


def test_r11_rejections_are_logged_too(rl):
    drain(rl, "a")
    with pytest.raises(RateLimited):
        rl.allow("a", 0.0)
    assert rl.log[-1].allowed is False


# R12 --------------------------------------------------------------------------

def test_r12_client_blocked_after_five_rejections(rl):
    drain(rl, "a")
    for _ in range(BLOCK_AFTER_REJECTIONS):
        with pytest.raises(RateLimited):
            rl.allow("a", 0.0)
    assert "a" in rl.blocked


def test_r12_four_rejections_do_not_block(rl):
    drain(rl, "a")
    for _ in range(BLOCK_AFTER_REJECTIONS - 1):
        with pytest.raises(RateLimited):
            rl.allow("a", 0.0)
    assert "a" not in rl.blocked


# R13 --------------------------------------------------------------------------

def test_r13_report_sorted_by_rejections_then_id(rl):
    for client in ("c", "b", "a"):
        drain(rl, client)
    for _ in range(3):
        with pytest.raises(RateLimited):
            rl.allow("b", 0.0)
    for _ in range(2):
        with pytest.raises(RateLimited):
            rl.allow("a", 0.0)
    for _ in range(2):
        with pytest.raises(RateLimited):
            rl.allow("c", 0.0)

    assert [(s.client_id, s.rejected) for s in rl.report()] == [
        ("b", 3), ("a", 2), ("c", 2),
    ]
