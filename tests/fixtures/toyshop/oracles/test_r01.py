import pytest
from shop import check_age


def test_exactly_eighteen_is_allowed():
    assert check_age(18) is True


def test_seventeen_is_refused():
    with pytest.raises(ValueError):
        check_age(17)
