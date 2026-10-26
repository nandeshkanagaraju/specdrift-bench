import pytest
from semver.version import Version


def test_patch_moves_only_when_asked():
    assert str(Version.parse("3.4.5").bump_prerelease()) == "3.4.5-rc.1"
    assert str(Version.parse("3.4.5").bump_prerelease(bump_when_empty=True)) == "3.4.6-rc.1"
    assert str(Version.parse("3.4.5-rc.1").bump_prerelease(bump_when_empty=True)) == "3.4.5-rc.2"
