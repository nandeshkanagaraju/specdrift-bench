import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_eviction_makes_room():
    cache = FIFOCache(3, getsizeof=int)
    cache["a"] = 1
    cache["b"] = 1
    cache["c"] = 1
    cache["d"] = 2
    assert len(cache) == 2
    assert cache.currsize == 3
    assert ("a" in cache) is False
    assert ("c" in cache) is True
    assert ("d" in cache) is True
