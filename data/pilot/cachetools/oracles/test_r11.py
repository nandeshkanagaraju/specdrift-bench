import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_least_used_goes_first():
    cache = LFUCache(2)
    cache["a"] = 1
    cache["b"] = 2
    cache["a"]
    cache["a"]
    cache["c"] = 3
    assert ("b" in cache) is False
    assert ("a" in cache) is True
