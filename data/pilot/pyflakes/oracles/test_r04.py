from pyflakes.api import iterSourceCode


def test_non_directories_are_yielded_as_given():
    assert list(iterSourceCode(["a.txt", "b"])) == ["a.txt", "b"]


def test_one_path_gives_that_path():
    assert list(iterSourceCode(["only.py"])) == ["only.py"]


def test_no_paths_give_nothing():
    assert list(iterSourceCode([])) == []
