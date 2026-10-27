import pytest
from xmltodict import unparse


def test_an_empty_dict_raises_for_a_full_document():
    with pytest.raises(ValueError):
        unparse({})


def test_an_empty_dict_is_an_empty_fragment():
    assert unparse({}, full_document=False) == ""
