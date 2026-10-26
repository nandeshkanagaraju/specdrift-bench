import io
from colorama import AnsiToWin32


def test_color_sequences_are_removed_when_stripping():
    stream = io.StringIO()
    AnsiToWin32(stream, strip=True, convert=False).write("\x1b[31mred\x1b[0m done")
    assert stream.getvalue() == "red done"


def test_color_sequences_are_kept_when_neither_stripping_nor_converting():
    stream = io.StringIO()
    AnsiToWin32(stream, strip=False, convert=False).write("\x1b[31mred\x1b[0m")
    assert stream.getvalue() == "\x1b[31mred\x1b[0m"
