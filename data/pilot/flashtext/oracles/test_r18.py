from flashtext import KeywordProcessor


def test_the_first_word_is_returned():
    assert KeywordProcessor().get_next_word("Big Apple") == "Big"


def test_a_sentence_without_a_boundary_is_returned_whole():
    assert KeywordProcessor().get_next_word("abc") == "abc"


def test_a_leading_boundary_gives_an_empty_word():
    assert KeywordProcessor().get_next_word(" x") == ""


def test_underscore_and_digits_belong_to_a_word():
    assert KeywordProcessor().get_next_word("a_1 b") == "a_1"
