from tabulate import tabulate


def test_pipe_line_marks_left_and_decimal_columns():
    assert tabulate([["a", 1]], headers=["x", "y"], tablefmt="pipe") == (
        "| x   |   y |\n|:----|----:|\n| a   |   1 |"
    )


def test_pipe_line_marks_center_and_right_columns():
    assert tabulate([["a", 1]], headers=["x", "y"], tablefmt="pipe", colalign=("center", "right")) == (
        "|  x  |   y |\n|:---:|----:|\n|  a  |   1 |"
    )
