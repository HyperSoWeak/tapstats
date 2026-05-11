import sqlite3
from datetime import date, timedelta

import pytest

from tapstats.db import (
    _init,
    flush,
    get_all_time_top_keys,
    get_day_stats,
    get_history,
    get_lifetime_stats,
    get_lifetime_totals,
    get_top_keys,
    get_week_totals,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    _init(c)
    return c


def _seed(conn, date_str, keys, mouse):
    flush(conn, {k: (i + 30, v) for i, (k, v) in enumerate(keys.items())}, mouse, date_str)


def test_get_history_excludes_scroll(conn):
    _seed(conn, "2026-05-10", {"KEY_A": 100}, {"left": 10, "scroll_up": 500, "scroll_down": 500})
    history = get_history(conn, days=7)
    assert len(history) == 1
    assert history[0]["total"] == 110  # 100 keys + 10 clicks, scroll excluded


def test_get_history_mode_keyboard(conn):
    _seed(conn, "2026-05-10", {"KEY_A": 100}, {"left": 20})
    rows = get_history(conn, days=7, mode="keyboard")
    assert rows[0]["total"] == 100


def test_get_history_mode_mouse(conn):
    _seed(conn, "2026-05-10", {"KEY_A": 100}, {"left": 20, "scroll_up": 999})
    rows = get_history(conn, days=7, mode="mouse")
    assert rows[0]["total"] == 20  # scroll excluded


def test_get_top_keys_no_limit(conn):
    keys = {f"KEY_{chr(65 + i)}": i + 1 for i in range(20)}
    _seed(conn, "2026-05-10", keys, {})
    all_keys = get_top_keys(conn, "2026-05-10", limit=None)
    assert len(all_keys) == 20


def test_get_lifetime_totals(conn):
    _seed(conn, "2026-05-10", {"KEY_A": 100}, {"left": 10, "scroll_up": 500})
    _seed(conn, "2026-05-11", {"KEY_B": 50}, {"right": 5})
    totals = get_lifetime_totals(conn)
    assert totals["keyboard"] == 150
    assert totals["mouse"] == 15   # scroll excluded
    assert totals["total"] == 165


def test_get_all_time_top_keys(conn):
    _seed(conn, "2026-05-10", {"KEY_A": 100, "KEY_B": 30}, {})
    _seed(conn, "2026-05-11", {"KEY_A": 50}, {})
    top = get_all_time_top_keys(conn, limit=5)
    assert top[0] == ("KEY_A", 150)
    assert top[1] == ("KEY_B", 30)


def test_get_week_totals(conn):
    today = date.today()
    _seed(conn, str(today), {"KEY_A": 100}, {"left": 10})
    _seed(conn, str(today - timedelta(days=3)), {"KEY_B": 200}, {})
    _seed(conn, str(today - timedelta(days=8)), {"KEY_C": 50}, {"right": 5})
    this_week, last_week = get_week_totals(conn)
    assert this_week == 310   # 100+10+200
    assert last_week == 55    # 50+5


def test_get_day_stats(conn):
    _seed(conn, "2026-05-10", {"KEY_A": 100, "KEY_B": 30}, {"left": 5, "scroll_up": 200})
    stats = get_day_stats(conn, "2026-05-10")
    assert stats["keyboard_total"] == 130
    assert stats["top_keys"][0] == ("KEY_A", 100)
    assert stats["mouse"]["left"] == 5
    assert stats["mouse"]["scroll_up"] == 200  # raw mouse data, unfiltered


def test_get_lifetime_stats(conn):
    _seed(conn, "2026-05-10", {"KEY_A": 100}, {"left": 10})
    _seed(conn, "2026-05-11", {"KEY_A": 50}, {"left": 5})
    stats = get_lifetime_stats(conn)
    assert stats["active_days"] == 2
    assert stats["first_date"] == "2026-05-10"
    assert stats["record_date"] == "2026-05-10"
    assert stats["record_total"] == 110
