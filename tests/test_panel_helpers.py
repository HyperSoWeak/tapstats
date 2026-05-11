import pytest

# These will be importable once panel.py is rewritten
from tapstats.panel import _bar, _compact, _heat_level, _spark_char


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
