from xmltodict import parse


def test_force_cdata_stores_text_under_the_cdata_key():
    assert parse("<a>x</a>", force_cdata=True) == {"a": {"#text": "x"}}


def test_text_is_plain_without_force_cdata():
    assert parse("<a>x</a>") == {"a": "x"}
