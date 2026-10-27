import pytest
from schema import Regex, SchemaError


def test_a_match_at_the_start_is_accepted():
    assert Regex("^foo").validate("foobar") == "foobar"


def test_a_match_in_the_middle_is_accepted():
    assert Regex("foo").validate("a foo b") == "a foo b"


def test_no_match_raises():
    with pytest.raises(SchemaError):
        Regex("^foo").validate("barfoo")
