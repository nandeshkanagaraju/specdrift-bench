"""The rate limiter. Each check carries the id of the rule it implements."""

from __future__ import annotations

from dataclasses import dataclass

from ratelimiter.bucket import TokenBucket
from ratelimiter.errors import ClientBlocked, RateLimited

BLOCK_AFTER_REJECTIONS = 5   # R12


@dataclass
class Decision:
    client_id: str
    allowed: bool
    reason: str
    tokens_left: float
    at: float


@dataclass
class ClientStats:
    client_id: str
    allowed: int = 0
    rejected: int = 0


class RateLimiter:
    def __init__(self) -> None:
        self.buckets: dict[str, TokenBucket] = {}
        self.stats: dict[str, ClientStats] = {}
        self.blocked: set[str] = set()
        self.log: list[Decision] = []

    # ---------------------------------------------------------------- buckets

    def bucket_for(self, client_id: str, now: float) -> TokenBucket:
        """R01/R02 - one bucket per client, created full on first use."""
        if client_id not in self.buckets:
            self.buckets[client_id] = TokenBucket(client_id=client_id, updated_at=now)
        bucket = self.buckets[client_id]
        bucket.refill(now)
        return bucket

    # -------------------------------------------------------------- admission

    def allow(self, client_id: str, now: float) -> Decision:
        """Admit or reject one request. Enforces R06 to R12."""
        stats = self._stats(client_id)

        # R09 - a blocked client is rejected whatever its bucket says.
        if client_id in self.blocked:
            self._reject(stats)
            raise ClientBlocked(f"client {client_id} is blocked")

        bucket = self.bucket_for(client_id, now)

        # R06/R08 - the bucket must hold at least one whole token.
        if not bucket.has_token():
            self._reject(stats)
            raise RateLimited(f"client {client_id} has {bucket.tokens:.2f} tokens")

        # R07/R10 - consume only now that every check above has passed.
        bucket.consume()
        stats.allowed += 1

        # R11 - the decision is logged after the token count has been updated.
        decision = Decision(
            client_id=client_id,
            allowed=True,
            reason="ok",
            tokens_left=bucket.tokens,
            at=now,
        )
        self.log.append(decision)
        return decision

    def block(self, client_id: str) -> None:
        self.blocked.add(client_id)

    # -------------------------------------------------------------- reporting

    def report(self) -> list[ClientStats]:
        """R13 - clients by rejection count, highest first, ties by client id."""
        return sorted(
            self.stats.values(),
            key=lambda s: (-s.rejected, s.client_id),
        )

    # --------------------------------------------------------------- internal

    def _reject(self, stats: ClientStats) -> None:
        stats.rejected += 1
        # R11 - the rejection is logged after the counter has been updated.
        self.log.append(
            Decision(
                client_id=stats.client_id,
                allowed=False,
                reason="rejected",
                tokens_left=self._tokens_left(stats.client_id),
                at=self.buckets[stats.client_id].updated_at
                if stats.client_id in self.buckets
                else 0.0,
            )
        )
        # R12 - blocked automatically at the rejection threshold.
        if stats.rejected >= BLOCK_AFTER_REJECTIONS:
            self.blocked.add(stats.client_id)

    def _tokens_left(self, client_id: str) -> float:
        bucket = self.buckets.get(client_id)
        return bucket.tokens if bucket else 0.0

    def _stats(self, client_id: str) -> ClientStats:
        if client_id not in self.stats:
            self.stats[client_id] = ClientStats(client_id=client_id)
        return self.stats[client_id]
