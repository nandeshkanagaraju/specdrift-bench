import io
from colorama import AnsiToWin32


def test_up_without_parameters_means_one():
    assert AnsiToWin32(io.StringIO()).extract_params("A", "") == (1,)


def test_down_without_parameters_means_one():
    assert AnsiToWin32(io.StringIO()).extract_params("B", "") == (1,)


def test_forward_without_parameters_means_one():
    assert AnsiToWin32(io.StringIO()).extract_params("C", "") == (1,)


def test_back_without_parameters_means_one():
    assert AnsiToWin32(io.StringIO()).extract_params("D", "") == (1,)


def test_another_command_gets_no_default():
    assert AnsiToWin32(io.StringIO()).extract_params("X", "") == ()
