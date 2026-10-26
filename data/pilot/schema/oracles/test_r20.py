from schema import SchemaError


def test_duplicate_messages_are_removed():
    assert SchemaError(["a", "a", "b"]).code == "a\nb"


def test_none_messages_are_dropped():
    assert SchemaError([None, "a"]).code == "a"


def test_order_is_preserved():
    assert SchemaError(["b", "a", "b"]).code == "b\na"
