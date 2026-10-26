import pytest
from semver.version import Version


def test_release_ranks_above_its_prerelease():
    assert Version.parse("1.2.3").compare("1.2.3-rc.1") == 1
    assert Version.parse("1.2.3-rc.1").compare("1.2.3") == -1
    assert Version.parse("1.2.3-rc.1").compare("1.2.3-rc.1") == 0
