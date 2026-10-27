from xmltodict import unparse


def test_nested_elements_are_indented_with_a_tab():
    assert unparse({"r": {"s": "g"}}, pretty=True, full_document=False) == "<r>\n\t<s>g</s>\n</r>"


def test_two_levels_of_nesting_use_two_tabs():
    assert unparse({"r": {"s": {"t": "g"}}}, pretty=True, full_document=False) == "<r>\n\t<s>\n\t\t<t>g</t>\n\t</s>\n</r>"
