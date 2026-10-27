import io
from colorama import AnsiToWin32


def test_m_without_parameters_means_zero():
    assert AnsiToWin32(io.StringIO()).extract_params("m", "") == (0,)


def test_j_without_parameters_means_zero():
    assert AnsiToWin32(io.StringIO()).extract_params("J", "") == (0,)


def test_k_without_parameters_means_zero():
    assert AnsiToWin32(io.StringIO()).extract_params("K", "") == (0,)


def test_explicit_parameters_are_kept():
    assert AnsiToWin32(io.StringIO()).extract_params("m", "1;31") == (1, 31)
