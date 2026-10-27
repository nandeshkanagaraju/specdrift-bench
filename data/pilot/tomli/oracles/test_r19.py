from tomli import loads


def test_a_second_array_header_adds_a_second_table():
    assert loads("[[p]]\na = 1\n[[p]]\na = 2") == {"p": [{"a": 1}, {"a": 2}]}


def test_one_array_header_gives_a_list_of_one_table():
    assert loads("[[p]]\na = 1") == {"p": [{"a": 1}]}
