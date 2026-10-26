import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_expire_returns_and_removes():
    cache = TTLCache(2, ttl=0, timer=int)
    cache["a"] = 1
    assert list(cache.expire()) == [("a", 1)]
    assert list(cache.expire()) == []
    assert len(cache) == 0
