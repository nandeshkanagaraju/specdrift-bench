import pytest
from semver.version import Version


def test_absent_parts_become_zero():
    assert str(Version.parse("1", optional_minor_and_patch=True)) == "1.0.0"
    assert str(Version.parse("1.2", optional_minor_and_patch=True)) == "1.2.0"
    assert str(Version.parse("1.2.3", optional_minor_and_patch=True)) == "1.2.3"


def test_absent_parts_are_refused_by_default():
    with pytest.raises(ValueError):
        Version.parse("1")
