import pytest
from semver.version import Version


def test_build_is_not_a_part():
    with pytest.raises(ValueError):
        Version.parse("1.2.3").next_version("build")


def test_unknown_part():
    with pytest.raises(ValueError):
        Version.parse("1.2.3").next_version("foo")


def test_empty_part():
    with pytest.raises(ValueError):
        Version.parse("1.2.3").next_version("")


def test_a_known_part_works():
    assert str(Version.parse("1.2.3").next_version("minor")) == "1.3.0"
