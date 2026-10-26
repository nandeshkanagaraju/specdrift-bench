from xmltodict import parse


def test_comments_are_added_when_asked():
    assert parse("<a><!--c-->1</a>", process_comments=True) == {"a": {"#comment": "c", "#text": "1"}}


def test_comments_are_ignored_by_default():
    assert parse("<a><!--c-->1</a>") == {"a": "1"}
