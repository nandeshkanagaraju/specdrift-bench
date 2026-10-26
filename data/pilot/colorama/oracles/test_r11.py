import io
from colorama import AnsiToWin32


def test_reset_all_writes_the_reset_sequence_when_not_stripping():
    stream = io.StringIO()
    AnsiToWin32(stream, strip=False, convert=False).reset_all()
    assert stream.getvalue() == "\x1b[0m"


def test_reset_all_writes_nothing_when_stripping():
    stream = io.StringIO()
    AnsiToWin32(stream, strip=True, convert=False).reset_all()
    assert stream.getvalue() == ""
