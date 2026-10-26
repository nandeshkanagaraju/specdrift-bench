from xmltodict import unparse


def test_keys_with_the_at_prefix_become_attributes():
    assert unparse({"a": {"@x": "1", "#text": "t"}}, full_document=False) == '<a x="1">t</a>'


def test_keys_without_the_prefix_become_child_elements():
    assert unparse({"a": {"x": "1"}}, full_document=False) == "<a><x>1</x></a>"
