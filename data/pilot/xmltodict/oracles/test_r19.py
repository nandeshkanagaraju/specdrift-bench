from xmltodict import unparse


def test_an_empty_list_produces_no_child_element():
    assert unparse({"a": {"b": []}}, full_document=False) == "<a></a>"


def test_a_list_with_an_empty_string_produces_an_empty_child():
    assert unparse({"a": {"b": [""]}}, full_document=False) == "<a><b></b></a>"
