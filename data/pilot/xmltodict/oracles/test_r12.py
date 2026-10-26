from xmltodict import unparse


def test_a_full_document_starts_with_the_declaration():
    assert unparse({"a": "1"}) == '<?xml version="1.0" encoding="utf-8"?>\n<a>1</a>'


def test_a_fragment_has_no_declaration():
    assert unparse({"a": "1"}, full_document=False) == "<a>1</a>"
