import pytest
from semver.version import Version


def test_default_token():
    assert Version.parse("3.4.5").bump_prerelease().prerelease == "rc.1"
    assert Version.parse("3.4.5").bump_prerelease("dev").prerelease == "dev.1"
    assert Version.parse("3.4.5").bump_prerelease("").prerelease == "1"
    assert Version.parse("3.4.5").bump_prerelease(None).prerelease == "rc.1"
