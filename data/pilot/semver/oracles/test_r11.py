import pytest
from semver.version import Version


def test_major_bump_clears_the_rest():
    assert str(Version.parse("3.4.5-rc.1+b.2").bump_major()) == "4.0.0"
    assert str(Version(0, 9, 9).bump_major()) == "1.0.0"
    assert Version.parse("3.4.5").bump_major().to_tuple() == (4, 0, 0, None, None)
