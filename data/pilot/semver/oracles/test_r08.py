import pytest
from semver.version import Version


def test_numbers_compare_by_value():
    assert Version.parse("1.0.0-rc.2").compare("1.0.0-rc.10") == -1
    assert Version.parse("1.0.0-rc.10").compare("1.0.0-rc.2") == 1
    assert Version.parse("1.0.0-9").compare("1.0.0-10") == -1
