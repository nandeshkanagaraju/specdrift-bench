import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_clear_resets_the_size():
    cache = Cache(5, getsizeof=int)
    cache["a"] = 2
    cache["b"] = 3
    assert cache.currsize == 5
    cache.clear()
    assert cache.currsize == 0
    assert len(cache) == 0
