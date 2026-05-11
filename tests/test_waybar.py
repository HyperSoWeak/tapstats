import json
import pytest
from datetime import date as date_type
from unittest.mock import MagicMock

from tapstats.waybar import _format_output, _fmt


def _cfg(display="total", compact=True, top_keys_count=3):
    cfg = MagicMock()
    cfg.waybar.display = display
    cfg.waybar.compact = compact
    cfg.waybar.top_keys_count = top_keys_count
    return cfg


def _data(kb=1000, clicks=200, scroll_up=500, lifetime_total=50000, top=None):
    return {
        "today": {
            "date": str(date_type.today()),
            "keyboard": {"total": kb, "top": top or [["KEY_SPACE", 300], ["KEY_E", 100]]},
            "mouse": {"left": clicks, "right": 0, "middle": 0,
                      "scroll_up": scroll_up, "scroll_down": 400},
        },
        "lifetime": {"keyboard": 40000, "mouse": 10000, "total": lifetime_total},
    }


def test_total_mode_text(tmp_path):
    result = json.loads(_format_output(_data(kb=1000, clicks=200), _cfg(display="total")))
    assert "1.2k" in result["text"]  # 1000+200=1200


def test_keyboard_mode_text():
    result = json.loads(_format_output(_data(kb=1000), _cfg(display="keyboard")))
    assert "󰌌" in result["text"]
    assert "1k" in result["text"]


def test_mouse_mode_text():
    result = json.loads(_format_output(_data(clicks=200), _cfg(display="mouse")))
    assert "󰍽" in result["text"]
    assert "200" in result["text"]


def test_both_mode_text():
    result = json.loads(_format_output(_data(kb=1000, clicks=200), _cfg(display="both")))
    assert "󰌌" in result["text"]
    assert "󰍽" in result["text"]


def test_tooltip_has_lifetime():
    result = json.loads(_format_output(_data(lifetime_total=50000), _cfg()))
    assert "50,000" in result["tooltip"]


def test_stale_date_returns_none():
    data = _data()
    data["today"]["date"] = "2020-01-01"
    assert _format_output(data, _cfg()) is None


def test_fmt_compact():
    assert _fmt(999) == "999"
    assert _fmt(1000) == "1k"
    assert _fmt(1500) == "1.5k"
    assert _fmt(2000) == "2k"
