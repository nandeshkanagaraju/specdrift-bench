"""Protection for the endpoints that cost money or write to disk.

``/api/check``, ``/api/sweep`` and the upload routes make paid LLM calls or store
user-supplied code, so they get an optional shared token, a per-client rate limit, and a
streaming body cap. Read-only routes stay open.
"""

from __future__ import annotations

import secrets
import shutil
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from specdrift.config import Settings

DATA_NOTICE = (
    "Uploaded code and specs are sent to the configured LLM provider when checked."
)


class RateLimiter:
    """Sliding one-minute window per client address."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client: str, now: float | None = None) -> None:
        if self.per_minute <= 0:
            return
        now = time.monotonic() if now is None else now
        window = self._hits[client]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.per_minute:
            retry = max(1, int(60.0 - (now - window[0])))
            raise HTTPException(429, "Too many requests.", headers={"Retry-After": str(retry)})
        window.append(now)


def make_guard(settings: Settings):
    """Build the FastAPI dependency: token (if configured), then rate limit."""
    limiter = RateLimiter(settings.api_rate_limit_per_min)

    def guard(request: Request) -> None:
        if settings.api_token:
            supplied = request.headers.get("x-api-token", "")
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                supplied = supplied or auth[7:]
            if not secrets.compare_digest(supplied, settings.api_token):
                raise HTTPException(401, "A valid API token is required.")
        limiter.check(request.client.host if request.client else "unknown")

    return guard


async def read_capped(request: Request, limit: int) -> bytes:
    """Read the request body, stopping as soon as it passes `limit` bytes."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, f"The upload is larger than {limit // 1000} KB.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"The upload is larger than {limit // 1000} KB.")
        chunks.append(chunk)
    return b"".join(chunks)


def prune_uploads(settings: Settings, now: float | None = None) -> int:
    """Delete stored uploads older than the configured TTL. Returns how many were removed."""
    root = settings.work_dir / "uploads"
    if not root.exists() or settings.upload_ttl_hours <= 0:
        return 0
    cutoff = (time.time() if now is None else now) - settings.upload_ttl_hours * 3600
    removed = 0
    for entry in root.iterdir():
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed
