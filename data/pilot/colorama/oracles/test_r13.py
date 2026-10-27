import io
from colorama import AnsiToWin32


def test_missing_position_parameters_default_to_one_one():
    assert AnsiToWin32(io.StringIO()).extract_params("H", "") == (1, 1)


def test_a_single_position_parameter_gets_a_second_default_of_one():
    assert AnsiToWin32(io.StringIO()).extract_params("H", "5") == (5, 1)


def test_two_position_parameters_are_kept():
    assert AnsiToWin32(io.StringIO()).extract_params("f", "3;4") == (3, 4)
