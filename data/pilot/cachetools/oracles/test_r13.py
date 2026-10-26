import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_expiry_boundary():
    cache = TTLCache(2, ttl=0, timer=int)
    cache["a"] = 1
    assert ("a" in cache) is False
    fresh = TTLCache(2, ttl=1, timer=int)
    fresh["a"] = 1
    assert ("a" in fresh) is True
