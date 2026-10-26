import pytest
from tomli import TOMLDecodeError, loads


def test_the_first_surrogate_raises():
    with pytest.raises(TOMLDecodeError):
        loads('a = "\\ud800"')


def test_the_last_surrogate_raises():
    with pytest.raises(TOMLDecodeError):
        loads('a = "\\udfff"')


def test_the_code_point_below_the_surrogates_is_accepted():
    assert loads('a = "\\ud7ff"') == {"a": "퟿"}


def test_the_code_point_above_the_surrogates_is_accepted():
    assert loads('a = "\\ue000"') == {"a": ""}
