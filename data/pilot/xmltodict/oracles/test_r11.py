import pytest
from xmltodict import ParsingInterrupted, parse


def test_a_false_callback_result_interrupts_parsing():
    with pytest.raises(ParsingInterrupted):
        parse("<a><b>1</b></a>", item_depth=2, item_callback=print)


def test_a_true_callback_result_lets_parsing_finish():
    assert parse("<a><b>1</b><b>2</b></a>", item_depth=2, item_callback=zip) is None
