import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_expired_item():
    cache = TTLCache(2, ttl=0, timer=int)
    cache["a"] = 1
    with pytest.raises(KeyError):
        cache["a"]


def test_live_item():
    fresh = TTLCache(2, ttl=1, timer=int)
    fresh["a"] = 1
    assert fresh["a"] == 1
