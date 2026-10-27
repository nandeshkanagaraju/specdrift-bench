import pytest
from flashtext import KeywordProcessor


def test_iterating_raises():
    with pytest.raises(NotImplementedError):
        iter(KeywordProcessor())


def test_get_all_keywords_is_the_supported_way():
    kp = KeywordProcessor()
    kp.add_keyword("a")
    assert kp.get_all_keywords() == {"a": "a"}
