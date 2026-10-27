import io
from colorama import AnsiToWin32


def test_nothing_to_do_means_no_wrapping():
    assert AnsiToWin32(io.StringIO(), strip=False, convert=False, autoreset=False).should_wrap() is False


def test_stripping_means_wrapping():
    assert AnsiToWin32(io.StringIO(), strip=True, convert=False).should_wrap() is True


def test_autoreset_means_wrapping():
    assert AnsiToWin32(io.StringIO(), strip=False, convert=False, autoreset=True).should_wrap() is True


def test_converting_means_wrapping():
    assert AnsiToWin32(io.StringIO(), strip=False, convert=True).should_wrap() is True
