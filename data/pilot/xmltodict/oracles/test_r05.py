from xmltodict import parse


def test_attributes_are_dropped_when_xml_attribs_is_false():
    assert parse('<a x="1">t</a>', xml_attribs=False) == {"a": "t"}


def test_attributes_are_kept_by_default():
    assert parse('<a x="1">t</a>') == {"a": {"@x": "1", "#text": "t"}}
