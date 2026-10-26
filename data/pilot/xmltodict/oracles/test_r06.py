from xmltodict import parse


def test_surrounding_whitespace_is_stripped_by_default():
    assert parse("<a>  x  </a>") == {"a": "x"}


def test_whitespace_only_text_becomes_none():
    assert parse("<a>   </a>") == {"a": None}


def test_whitespace_is_kept_when_strip_whitespace_is_false():
    assert parse("<a>  x  </a>", strip_whitespace=False) == {"a": "  x  "}
