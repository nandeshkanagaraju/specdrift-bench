import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_setdefault_stores_and_keeps():
    cache = Cache(2)
    assert cache.setdefault("a", 7) == 7
    assert cache["a"] == 7
    assert cache.setdefault("a", 9) == 7
