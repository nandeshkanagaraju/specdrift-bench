from xmltodict import parse


def test_force_list_wraps_a_single_child():
    assert parse("<a><b>1</b></a>", force_list=("b",)) == {"a": {"b": ["1"]}}


def test_force_list_leaves_other_tags_alone():
    assert parse("<a><b>1</b></a>", force_list=("c",)) == {"a": {"b": "1"}}
