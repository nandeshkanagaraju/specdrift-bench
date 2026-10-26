import pytest
from semver.version import Version


def test_patch_bump_drops_prerelease_and_build():
    assert str(Version.parse("3.4.5-rc.1+b.2").bump_patch()) == "3.4.6"
    assert str(Version.parse("3.4.9").bump_patch()) == "3.4.10"
