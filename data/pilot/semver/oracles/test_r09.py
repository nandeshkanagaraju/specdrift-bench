import pytest
from semver.version import Version


def test_a_bare_version_means_equal():
    assert Version.parse("4.0.4").match("4.0.4") is True
    assert Version.parse("4.0.4").match("4.0.5") is False
    assert Version.parse("1.0.0").match("2.0.0") is False
