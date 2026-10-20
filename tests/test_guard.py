import os
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from specdrift.api.app import create_app
from specdrift.api.guard import RateLimiter, prune_uploads
from specdrift.config import REPO_ROOT


def _client(settings, **overrides):
    settings.results_dir = REPO_ROOT / "results"
    settings.cases_dir = REPO_ROOT / "cases"
    settings.demo_pacing = False
    settings.api_rate_limit_per_min = 0
    for key, value in overrides.items():
        setattr(settings, key, value)
    return TestClient(create_app(settings))


def test_rate_limiter_blocks_after_the_quota_and_recovers():
    limiter = RateLimiter(per_minute=2)
    limiter.check("a", now=0.0)
    limiter.check("a", now=1.0)
    with pytest.raises(HTTPException) as exc:
        limiter.check("a", now=2.0)
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers
    limiter.check("b", now=2.0)           # another client is unaffected
    limiter.check("a", now=61.0)          # the window has moved on


def test_costly_endpoint_requires_the_token_when_one_is_set(settings):
    client = _client(settings, api_token="s3cret")
    body = {"name": "x", "spec": "- **R01** a", "files": []}
    assert client.post("/api/uploads", json=body).status_code == 401
    assert client.post("/api/uploads", json=body, headers={"X-API-Token": "wrong"}).status_code == 401
    ok = client.post("/api/uploads", json=body, headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code != 401


def test_read_only_routes_stay_open_even_with_a_token(settings):
    assert _client(settings, api_token="s3cret").get("/api/summary").status_code == 200


def test_rate_limit_applies_to_post_endpoints(settings):
    client = _client(settings, api_rate_limit_per_min=2)
    codes = [client.post("/api/reload").status_code for _ in range(3)]
    assert codes[:2] == [200, 200] and codes[2] == 429


def test_oversized_archive_is_rejected_before_it_is_buffered(settings):
    client = _client(settings)
    too_big = b"0" * 1_600_000
    assert client.post("/api/uploads/archive", content=too_big).status_code == 413


def test_upload_response_carries_the_data_notice(settings, tmp_path):
    client = _client(settings, work_dir=tmp_path)
    body = {
        "name": "x",
        "spec": "- **R01** The value MUST be 1.",
        "files": [{"path": "src/m.py", "source": "VALUE = 1\n"}],
    }
    response = client.post("/api/uploads", json=body)
    assert response.status_code == 200, response.text
    assert "LLM provider" in response.headers["x-data-notice"]


def test_prune_uploads_removes_only_expired_directories(settings, tmp_path):
    settings.work_dir = tmp_path
    settings.upload_ttl_hours = 1
    old, fresh = tmp_path / "uploads" / "old", tmp_path / "uploads" / "fresh"
    old.mkdir(parents=True)
    fresh.mkdir(parents=True)
    stale = time.time() - 7200
    os.utime(old, (stale, stale))

    assert prune_uploads(settings) == 1
    assert not old.exists() and fresh.exists()
