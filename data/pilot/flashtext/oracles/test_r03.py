from flashtext import KeywordProcessor


def test_the_clean_name_defaults_to_the_keyword():
    kp = KeywordProcessor()
    kp.add_keyword("java")
    assert kp.get_keyword("java") == "java"


def test_an_explicit_clean_name_wins():
    kp = KeywordProcessor()
    kp.add_keyword("j2ee", "Java")
    assert kp.get_keyword("j2ee") == "Java"
