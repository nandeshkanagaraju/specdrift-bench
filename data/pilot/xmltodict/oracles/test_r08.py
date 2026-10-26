from xmltodict import parse


def test_prefixes_are_unchanged_by_default():
    assert list(parse('<a:r xmlns:a="http://a.com/"/>')) == ["a:r"]


def test_prefixes_are_expanded_when_asked():
    assert list(parse('<a:r xmlns:a="http://a.com/"/>', process_namespaces=True)) == ["http://a.com/:r"]
