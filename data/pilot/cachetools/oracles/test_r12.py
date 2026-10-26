import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_empty_cache():
    cache = LRUCache(2)
    with pytest.raises(KeyError):
        cache.popitem()


def test_a_filled_cache_gives_its_oldest():
    cache = LRUCache(2)
    cache["a"] = 1
    assert cache.popitem() == ("a", 1)
