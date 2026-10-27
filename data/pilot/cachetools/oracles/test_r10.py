import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_reading_refreshes_a_key():
    cache = LRUCache(2)
    cache["a"] = 1
    cache["b"] = 2
    cache["a"]
    cache["c"] = 3
    assert ("b" in cache) is False
    assert ("a" in cache) is True
    assert ("c" in cache) is True
