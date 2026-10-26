import pytest
from semver.version import Version


def test_plain_text():
    with pytest.raises(ValueError):
        Version.parse("1.0.0").match("abc")


def test_unknown_operator():
    with pytest.raises(ValueError):
        Version.parse("1.0.0").match("=1.0.0")


def test_tilde():
    with pytest.raises(ValueError):
        Version.parse("1.0.0").match("~1.0.0")


def test_a_known_operator_works():
    assert Version.parse("1.0.0").match(">=1.0.0") is True
