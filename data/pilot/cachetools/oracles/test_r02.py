import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_value_larger_than_maxsize():
    cache = Cache(2, getsizeof=len)
    with pytest.raises(ValueError):
        cache["a"] = "abc"


def test_value_equal_to_maxsize_fits():
    cache = Cache(2, getsizeof=len)
    cache["a"] = "ab"
    assert cache.currsize == 2
    assert cache["a"] == "ab"
