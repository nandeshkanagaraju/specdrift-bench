import pytest
from xmltodict import parse


def test_a_declared_entity_raises_by_default():
    with pytest.raises(ValueError):
        parse('<!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>')


def test_a_declared_entity_is_expanded_when_entities_are_enabled():
    assert parse('<!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>', disable_entities=False) == {"a": "x"}
