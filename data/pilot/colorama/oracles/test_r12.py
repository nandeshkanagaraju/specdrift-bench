import io
from colorama import AnsiToWin32


def test_autoreset_appends_the_reset_sequence_after_a_write():
    stream = io.StringIO()
    AnsiToWin32(stream, strip=False, convert=False, autoreset=True).write("hi")
    assert stream.getvalue() == "hi\x1b[0m"


def test_without_autoreset_nothing_is_appended():
    stream = io.StringIO()
    AnsiToWin32(stream, strip=False, convert=False).write("hi")
    assert stream.getvalue() == "hi"
