import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_first_inserted_goes_first():
    cache = FIFOCache(3)
    cache["a"] = 1
    cache["b"] = 2
    cache["c"] = 3
    assert cache.popitem() == ("a", 1)
    assert cache.popitem() == ("b", 2)
