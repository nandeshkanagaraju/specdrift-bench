import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_negative_size():
    cache = Cache(5, getsizeof=int)
    with pytest.raises(ValueError):
        cache["a"] = -1


def test_zero_size_is_allowed():
    cache = Cache(5, getsizeof=int)
    cache["a"] = 0
    cache["b"] = 5
    assert cache.currsize == 5
