import pytest
from semver.version import Version


def test_format():
    assert str(Version(1, 2, 3)) == "1.2.3"
    assert str(Version(1, 2, 3, "rc.1")) == "1.2.3-rc.1"
    assert str(Version(1, 2, 3, None, "b.2")) == "1.2.3+b.2"
    assert str(Version(1, 2, 3, "rc.1", "b.2")) == "1.2.3-rc.1+b.2"
