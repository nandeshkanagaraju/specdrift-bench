import pytest
from cachetools import Cache, FIFOCache, LFUCache, LRUCache, TTLCache


def test_negative_maxsize():
    with pytest.raises(ValueError):
        Cache(-1)


def test_zero_and_positive_maxsize():
    assert Cache(0).maxsize == 0
    assert Cache(3).maxsize == 3
