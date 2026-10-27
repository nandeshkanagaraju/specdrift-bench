import pytest
from semver.version import Version


def test_build_is_ignored():
    assert Version.parse("1.2.3+a").compare("1.2.3+b") == 0
    assert Version.parse("1.2.3+a").compare("1.2.3") == 0
    assert Version.parse("1.2.3-rc.1+z").compare("1.2.3-rc.1+a") == 0
