import pytest
from semver.version import Version


def test_negative_major():
    with pytest.raises(ValueError):
        Version(-1)


def test_negative_minor():
    with pytest.raises(ValueError):
        Version(1, -1)


def test_negative_patch():
    with pytest.raises(ValueError):
        Version(1, 1, -1)


def test_zero_is_allowed():
    assert str(Version(0, 0, 0)) == "0.0.0"
