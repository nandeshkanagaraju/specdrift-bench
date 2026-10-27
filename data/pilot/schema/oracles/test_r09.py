from schema import Optional, Schema


def test_an_absent_optional_key_gets_its_default():
    assert Schema({"a": int, Optional("b", default=5): int}).validate({"a": 1}) == {"a": 1, "b": 5}


def test_a_present_optional_key_keeps_its_value():
    assert Schema({"a": int, Optional("b", default=5): int}).validate({"a": 1, "b": 7}) == {"a": 1, "b": 7}
