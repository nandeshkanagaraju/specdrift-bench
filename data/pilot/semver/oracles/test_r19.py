import pytest
from semver.version import Version


def test_negative_index():
    with pytest.raises(IndexError):
        Version(1, 2, 3)[-1]


def test_negative_slice_stop():
    with pytest.raises(IndexError):
        Version(1, 2, 3)[0:-1]


def test_positive_index():
    assert Version(1, 2, 3)[0] == 1
    assert Version(1, 2, 3)[2] == 3
