import io
import pytest
from tomli import load


def test_a_text_mode_file_raises():
    with pytest.raises(TypeError):
        load(io.StringIO("a = 1"))


def test_a_binary_file_parses():
    assert load(io.BytesIO(b"a = 1")) == {"a": 1}
