import pytest
from semver.version import Version


def test_missing_patch():
    with pytest.raises(ValueError):
        Version.parse("1.2")


def test_leading_v():
    with pytest.raises(ValueError):
        Version.parse("v1.2.3")


def test_plain_text():
    with pytest.raises(ValueError):
        Version.parse("not-a-version")


def test_valid_string():
    assert str(Version.parse("1.2.3-rc.1+b.2")) == "1.2.3-rc.1+b.2"
