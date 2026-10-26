import pytest
from semver.version import Version


def test_integer_argument():
    with pytest.raises(TypeError):
        Version.parse(12)


def test_none_argument():
    with pytest.raises(TypeError):
        Version.parse(None)


def test_bytes_are_accepted():
    assert str(Version.parse(b"1.2.3")) == "1.2.3"
    assert str(Version.parse("1.2.3")) == "1.2.3"
