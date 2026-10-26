import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_missing_key_without_default():
    cache = Cache(2)
    with pytest.raises(KeyError):
        cache.pop("x")


def test_default_and_present_key():
    cache = Cache(2)
    assert cache.pop("x", 5) == 5
    cache["a"] = 1
    assert cache.pop("a") == 1
    assert ("a" in cache) is False
