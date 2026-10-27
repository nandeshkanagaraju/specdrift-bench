import pytest
from semver.version import Version


def test_leading_zero_in_major():
    with pytest.raises(ValueError):
        Version.parse("01.2.3")


def test_zero_major_is_allowed():
    assert str(Version.parse("0.2.3")) == "0.2.3"
    assert str(Version.parse("10.2.3")) == "10.2.3"
