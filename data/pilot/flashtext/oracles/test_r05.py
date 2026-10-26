import pytest
from flashtext import KeywordProcessor


def test_a_string_raises():
    with pytest.raises(AttributeError):
        KeywordProcessor().add_keywords_from_list("java")


def test_a_list_is_accepted():
    kp = KeywordProcessor()
    kp.add_keywords_from_list(["java", "python"])
    assert len(kp) == 2
