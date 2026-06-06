import pytest

# These will be importable once panel.py is rewritten
from tapstats.panel import (
    _bar,
    _click_total,
    _compact,
    _delta_text,
    _heat_level,
    _scroll_total,
    _spark_char,
    _trend_text,
)


def test_heat_level_zero():
    assert _heat_level(0, 100) == 0


def test_heat_level_max():
    assert _heat_level(100, 100) == 8


def test_heat_level_half():
    assert _heat_level(50, 100) == 4


def test_heat_level_zero_max():
    assert _heat_level(0, 0) == 0


def test_bar_full():
    assert _bar(10, 10, 10) == "█" * 10


def test_bar_empty():
    assert _bar(0, 10, 10) == " " * 10


def test_bar_zero_max():
    assert _bar(5, 0, 10) == " " * 10


def test_spark_char_min():
    assert _spark_char(0, 10) == " "


def test_spark_char_max():
    assert _spark_char(10, 10) == "█"


def test_compact_below_1000():
    assert _compact(999) == "999"


def test_compact_exact_1000():
    assert _compact(1000) == "1k"


def test_compact_1500():
    assert _compact(1500) == "1.5k"


def test_compact_2000():
    assert _compact(2000) == "2k"


def test_click_total_excludes_scroll():
    assert _click_total({"left": 10, "right": 5, "middle": 2, "scroll_up": 100}) == 17


def test_scroll_total_combines_directions():
    assert _scroll_total({"scroll_up": 100, "scroll_down": 50}) == 150


def test_delta_text_positive_negative_and_zero_previous():
    assert _delta_text(112, 100) == "+12.0%"
    assert _delta_text(80, 100) == "-20.0%"
    assert _delta_text(80, 0) == ""


def test_trend_text_uses_spark_chars():
    rows = [{"total": 0}, {"total": 50}, {"total": 100}]
    assert _trend_text(rows) == " ▄█"
