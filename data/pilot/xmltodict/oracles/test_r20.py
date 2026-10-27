import pytest
from xmltodict import unparse


def test_an_unknown_bytes_errors_handler_raises():
    with pytest.raises(ValueError):
        unparse({"a": "1"}, bytes_errors="no-such-handler")


def test_a_known_bytes_errors_handler_is_accepted():
    assert unparse({"a": "1"}, full_document=False, bytes_errors="strict") == "<a>1</a>"
