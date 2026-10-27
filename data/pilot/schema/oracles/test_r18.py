from schema import Schema


def test_valid_data_gives_true():
    assert Schema(int).is_valid(1) is True


def test_invalid_data_gives_false():
    assert Schema(int).is_valid("x") is False
