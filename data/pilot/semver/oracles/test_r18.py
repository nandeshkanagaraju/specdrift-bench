import pytest
from semver.version import Version


def test_a_lower_other_minor_is_incompatible():
    assert Version(1, 1, 0).is_compatible(Version(1, 0, 0)) is False
    assert Version(1, 1, 0).is_compatible(Version(1, 1, 0)) is True
    assert Version(1, 1, 0).is_compatible(Version(1, 2, 0)) is True
