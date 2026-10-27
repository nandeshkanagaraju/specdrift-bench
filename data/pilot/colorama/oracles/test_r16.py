import pytest
from colorama import deinit, init
from colorama.initialise import _wipe_internal_state_for_tests


def test_wrap_false_with_autoreset_raises():
    with pytest.raises(ValueError):
        init(wrap=False, autoreset=True)


def test_wrap_false_with_strip_raises():
    with pytest.raises(ValueError):
        init(wrap=False, strip=True)


def test_wrap_false_with_convert_raises():
    with pytest.raises(ValueError):
        init(wrap=False, convert=True)


def test_wrap_true_with_an_option_is_accepted():
    assert init(autoreset=True) is None
    deinit()
    _wipe_internal_state_for_tests()
