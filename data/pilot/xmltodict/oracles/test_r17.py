import pytest
from xmltodict import unparse


def test_an_opening_angle_bracket_in_a_name_raises():
    with pytest.raises(ValueError):
        unparse({"a<b": "1"}, full_document=False)


def test_a_closing_angle_bracket_in_a_name_raises():
    with pytest.raises(ValueError):
        unparse({"a>b": "1"}, full_document=False)


def test_an_ordinary_name_is_accepted():
    assert unparse({"ab": "1"}, full_document=False) == "<ab>1</ab>"
