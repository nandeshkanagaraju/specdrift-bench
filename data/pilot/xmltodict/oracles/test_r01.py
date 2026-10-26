from xmltodict import parse


def test_attribute_names_get_an_at_prefix():
    assert parse('<a x="1"/>') == {"a": {"@x": "1"}}


def test_two_attributes_both_get_the_prefix():
    assert parse('<a x="1" y="2"/>') == {"a": {"@x": "1", "@y": "2"}}
