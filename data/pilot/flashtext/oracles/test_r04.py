import pytest
from flashtext import KeywordProcessor


def test_a_string_value_raises():
    with pytest.raises(AttributeError):
        KeywordProcessor().add_keywords_from_dict({"java": "java_2e"})


def test_a_list_value_is_accepted():
    kp = KeywordProcessor()
    kp.add_keywords_from_dict({"java": ["java_2e", "java programing"]})
    assert kp.get_keyword("java_2e") == "java"
