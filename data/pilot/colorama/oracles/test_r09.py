import io
from colorama import AnsiToWin32


def test_a_stream_that_is_not_a_terminal_is_stripped_by_default():
    assert AnsiToWin32(io.StringIO()).strip is True


def test_the_strip_argument_overrides_the_default():
    assert AnsiToWin32(io.StringIO(), strip=False).strip is False
