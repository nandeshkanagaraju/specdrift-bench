from xmltodict import unparse


def test_true_is_written_in_lowercase():
    assert unparse({"a": True}, full_document=False) == "<a>true</a>"


def test_false_is_written_in_lowercase():
    assert unparse({"a": False}, full_document=False) == "<a>false</a>"
