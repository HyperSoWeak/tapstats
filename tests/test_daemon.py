import json
from datetime import date as date_type
from unittest.mock import MagicMock, patch

from tapstats.daemon import Daemon


def _make_daemon(tmp_path, today_keys=None, today_mouse=None,
                  lifetime_kb_base=900, lifetime_mouse_base=190):
    runtime_path = tmp_path / "tapstats.json"

    with patch("tapstats.daemon.get_config") as mock_cfg, \
         patch("tapstats.daemon.get_db", return_value=MagicMock()), \
         patch("tapstats.daemon.load_today",
               return_value={"keys": {"KEY_A": 50}, "mouse": {"left": 10}}), \
         patch("tapstats.daemon.get_lifetime_totals",
               return_value={"keyboard": 950, "mouse": 200, "total": 1150}):

        mock_cfg.return_value.daemon.tick_interval = 5.0
        mock_cfg.return_value.daemon.flush_interval = 30.0
        mock_cfg.return_value.waybar.signal = 8

        d = Daemon()

    d.today_keys = today_keys or {}
    d.today_mouse = today_mouse or {}
    d._today_date = str(date_type.today())
    d.lifetime_kb_base = lifetime_kb_base
    d.lifetime_mouse_base = lifetime_mouse_base

    return d, runtime_path


def test_write_runtime_has_today_and_lifetime(tmp_path):
    d, path = _make_daemon(tmp_path,
                            today_keys={"KEY_A": 80, "KEY_B": 30},
                            today_mouse={"left": 15, "right": 5, "scroll_up": 100})

    with patch("tapstats.daemon.RUNTIME_JSON", path):
        d._write_runtime()

    data = json.loads(path.read_text())
    assert "today" in data
    assert "lifetime" in data


def test_write_runtime_today_structure(tmp_path):
    d, path = _make_daemon(tmp_path,
                            today_keys={"KEY_A": 80, "KEY_B": 30},
                            today_mouse={"left": 15, "right": 5, "scroll_up": 100})

    with patch("tapstats.daemon.RUNTIME_JSON", path):
        d._write_runtime()

    today = json.loads(path.read_text())["today"]
    assert today["date"] == str(date_type.today())
    assert today["keyboard"]["total"] == 110  # 80+30
    assert today["mouse"]["left"] == 15
    assert today["mouse"]["scroll_up"] == 100  # raw scroll preserved


def test_write_runtime_lifetime_excludes_scroll(tmp_path):
    # lifetime_kb_base=900, lifetime_mouse_base=190
    # today: 110 keys, 20 clicks (15+5), 100 scroll
    d, path = _make_daemon(tmp_path,
                            today_keys={"KEY_A": 80, "KEY_B": 30},
                            today_mouse={"left": 15, "right": 5, "scroll_up": 100},
                            lifetime_kb_base=900, lifetime_mouse_base=190)

    with patch("tapstats.daemon.RUNTIME_JSON", path):
        d._write_runtime()

    lifetime = json.loads(path.read_text())["lifetime"]
    assert lifetime["keyboard"] == 1010   # 900 + 110
    assert lifetime["mouse"] == 210       # 190 + 20 (scroll excluded)
    assert lifetime["total"] == 1220


def test_date_rollover_refreshes_lifetime_base_from_db(tmp_path):
    d, path = _make_daemon(tmp_path, lifetime_kb_base=5000, lifetime_mouse_base=1000)
    d._today_date = "2026-05-11"

    with patch("tapstats.daemon.date_type") as mock_date, \
         patch.object(d, "_do_flush"), \
         patch.object(d, "_write_runtime"), \
         patch("tapstats.daemon.get_lifetime_totals",
               return_value={"keyboard": 6000, "mouse": 1200, "total": 7200}):
        mock_date.today.return_value.__str__ = lambda _: "2026-05-12"
        d._check_date_rollover()

    assert d.lifetime_kb_base == 6000
    assert d.lifetime_mouse_base == 1200
