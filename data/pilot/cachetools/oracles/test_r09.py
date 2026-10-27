import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_an_updated_key_moves_to_the_end():
    cache = FIFOCache(2)
    cache["a"] = 1
    cache["b"] = 2
    cache["a"] = 3
    cache["c"] = 4
    assert ("b" in cache) is False
    assert ("a" in cache) is True
    assert cache["a"] == 3
