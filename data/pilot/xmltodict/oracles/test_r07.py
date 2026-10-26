from xmltodict import parse


def test_a_mapped_uri_becomes_its_prefix():
    assert list(parse('<a:r xmlns:a="http://a.com/"/>', process_namespaces=True, namespaces={"http://a.com/": "ns"})) == ["ns:r"]


def test_an_unmapped_uri_stays_in_the_name():
    assert list(parse('<a:r xmlns:a="http://a.com/"/>', process_namespaces=True, namespaces={"http://b.com/": "ns"})) == ["http://a.com/:r"]
