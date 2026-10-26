import io
from colorama.initialise import wrap_stream


def test_wrap_false_returns_the_stream_itself():
    stream = io.StringIO()
    assert (wrap_stream(stream, None, True, True, False) is stream) is True


def test_wrap_true_with_stripping_returns_a_wrapper():
    stream = io.StringIO()
    assert (wrap_stream(stream, None, True, False, True) is stream) is False


def test_wrap_true_with_nothing_to_do_returns_the_stream_itself():
    stream = io.StringIO()
    assert (wrap_stream(stream, False, False, False, True) is stream) is True
