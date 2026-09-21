"""One token bucket per client. All arithmetic is in float seconds and tokens."""

from __future__ import annotations

from dataclasses import dataclass

from ratelimiter.errors import InvalidClock

BURST_LIMIT = 10.0      # R03
REFILL_PER_SECOND = 2.0  # R04


@dataclass
class TokenBucket:
    """R01 - one bucket belongs to exactly one client."""

    client_id: str
    tokens: float = BURST_LIMIT   # R02 - a new bucket starts full.
    updated_at: float = 0.0

    def refill(self, now: float) -> None:
        """R04/R05 - add 2 tokens per elapsed second, never past the burst limit."""
        if now < self.updated_at:
            raise InvalidClock(f"time went backwards: {now} < {self.updated_at}")

        elapsed = now - self.updated_at
        # R04 - the refill rate.
        self.tokens += elapsed * REFILL_PER_SECOND
        # R05 - the bucket is capped at the burst limit.
        if self.tokens > BURST_LIMIT:
            self.tokens = BURST_LIMIT
        self.updated_at = now

    def has_token(self) -> bool:
        """R06/R08 - a request needs at least one whole token."""
        return self.tokens >= 1.0

    def consume(self) -> None:
        """R07 - an allowed request costs exactly one token."""
        self.tokens -= 1.0
