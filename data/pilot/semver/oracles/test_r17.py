import pytest
from semver.version import Version


def test_different_majors_are_incompatible():
    assert Version(1, 0, 0).is_compatible(Version(2, 0, 0)) is False
    assert Version(2, 0, 0).is_compatible(Version(1, 0, 0)) is False
    assert Version(1, 0, 0).is_compatible(Version(1, 1, 0)) is True
