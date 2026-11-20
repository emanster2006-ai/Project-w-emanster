"""Unit tests for the numeric grounding check."""

from security.grounding import ungrounded_numbers

CHUNKS = [
    {"text": "Net sales were $394,328 million in 2022, up 7.8% from 2021."},
    {"text": "Operating income was 119,437 million."},
]


def test_grounded_figures_pass():
    answer = "Apple's net sales were $394,328 million, up 7.8%."
    assert ungrounded_numbers(answer, CHUNKS) == []


def test_invented_figure_is_flagged():
    answer = "Net sales were $394,328 million and net income was $99,803 million."
    assert ungrounded_numbers(answer, CHUNKS) == ["99803"]


def test_commas_and_trailing_zeros_normalised():
    assert ungrounded_numbers("Growth was 7.80%.", CHUNKS) == []


def test_small_integers_ignored():
    assert ungrounded_numbers("Three segments: 1, 2 and 3.", CHUNKS) == []
