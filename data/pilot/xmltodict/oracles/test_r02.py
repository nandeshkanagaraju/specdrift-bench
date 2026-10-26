from xmltodict import parse


def test_two_siblings_with_the_same_tag_become_a_list():
    assert parse("<a><b>1</b><b>2</b></a>") == {"a": {"b": ["1", "2"]}}


def test_three_siblings_with_the_same_tag_stay_in_one_list():
    assert parse("<a><b>1</b><b>2</b><b>3</b></a>") == {"a": {"b": ["1", "2", "3"]}}


def test_a_single_child_is_not_a_list():
    assert parse("<a><b>1</b></a>") == {"a": {"b": "1"}}
