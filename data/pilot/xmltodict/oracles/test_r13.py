import pytest
from xmltodict import unparse


def test_two_roots_in_a_full_document_raise():
    with pytest.raises(ValueError):
        unparse({"a": "1", "b": "2"})


def test_two_roots_are_allowed_in_a_fragment():
    assert unparse({"a": "1", "b": "2"}, full_document=False) == "<a>1</a><b>2</b>"
