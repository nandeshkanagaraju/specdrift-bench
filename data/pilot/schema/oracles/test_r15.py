import pytest
from schema import Use


def test_a_non_callable_raises_a_type_error():
    with pytest.raises(TypeError):
        Use(5)


def test_a_callable_is_accepted():
    assert Use(int).validate("5") == 5
