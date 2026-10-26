from pyflakes.api import isPythonFile


def test_a_name_ending_with_a_tilde_is_not_python():
    assert isPythonFile("notes~") is False


def test_a_py_name_is_python():
    assert isPythonFile("mod.py") is True


def test_a_missing_file_without_an_extension_is_not_python():
    assert isPythonFile("no_such_file_for_pyflakes") is False
