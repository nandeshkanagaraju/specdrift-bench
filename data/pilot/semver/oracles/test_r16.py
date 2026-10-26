import pytest
from semver.version import Version


def test_patch_of_a_prerelease_finalises_it():
    assert str(Version.parse("1.2.3-rc.1+b").next_version("patch")) == "1.2.3"
    assert str(Version.parse("1.2.3").next_version("patch")) == "1.2.4"
