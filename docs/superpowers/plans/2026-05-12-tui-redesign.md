# TUI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign tapstats into a 4-tab TUI (TODAY / KEYS / HISTORY / LIFETIME), add keyboard heatmap, restructure daemon runtime JSON, and add `total` mode to waybar.

**Architecture:** Textual `ContentSwitcher` routes between four view widgets; each view owns its own keybindings. Daemon gains `lifetime_kb_base` / `lifetime_mouse_base` counters loaded from DB on startup and emits a restructured JSON with `today` + `lifetime` top-level keys. All consumers update read paths accordingly.

**Tech Stack:** Python 3.11+, Textual, SQLite (stdlib sqlite3), evdev, uv, pytest

---

## File Map

| File | Change |
|------|--------|
| `src/tapstats/db.py` | New query functions; `get_history` mode param; `get_top_keys` `limit=None`; scroll exclusion |
| `src/tapstats/daemon.py` | `lifetime_kb_base` / `lifetime_mouse_base`; restructured JSON output |
| `src/tapstats/waybar.py` | Extract `_format_output`; update read paths; add `"total"` mode |
| `src/tapstats/config.py` | `WaybarConfig.display` default → `"total"` |
| `src/tapstats/panel.py` | Full rewrite: 4-tab app, heatmap, cursor nav, drill-down |
| `tests/__init__.py` | Created (empty) |
| `tests/test_db.py` | All new db functions |
| `tests/test_daemon.py` | `_write_runtime` JSON structure |
| `tests/test_waybar.py` | `_format_output` for each display mode |
| `tests/test_panel_helpers.py` | `_heat_level`, `_bar`, `_spark_char`, `_compact` |

---

## Task 1: Add pytest + fix db.py

**Files:**
- Modify: `src/tapstats/db.py`
- Create: `tests/__init__.py`, `tests/test_db.py`

New/changed signatures:
- `get_top_keys(conn, date, limit=15)` — `limit=None` returns all keys for date
- `get_history(conn, days=14, mode="total")` — `mode`: `"total"` | `"keyboard"` | `"mouse"`; scroll excluded from all
- `get_lifetime_totals(conn) -> dict` — `{"keyboard": int, "mouse": int, "total": int}`
- `get_lifetime_stats(conn) -> dict` — adds `first_date`, `active_days`, `record_date`, `record_total`
- `get_all_time_top_keys(conn, limit=20) -> list[tuple[str, int]]`
- `get_week_totals(conn) -> tuple[int, int]` — `(this_7d_total, prev_7d_total)`
- `get_day_stats(conn, date, top_limit=15) -> dict` — `{keyboard_total, top_keys, mouse}`

- [ ] **Step 1: Install pytest**

```bash
cd /home/hyper/proj/tapstats && uv add --dev pytest
```

- [ ] **Step 2: Create tests dir**

```bash
mkdir -p tests && touch tests/__init__.py
```

- [ ] **Step 3: Write failing tests**

Create `tests/test_db.py`:

```python
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
```

- [ ] **Step 4: Run tests — expect failures**

```bash
uv run pytest tests/test_db.py -v 2>&1 | head -40
```

Expected: `ImportError` or failures on missing functions.

- [ ] **Step 5: Rewrite db.py**

Replace `src/tapstats/db.py` entirely:

```python
import sqlite3
from datetime import date as date_type
from pathlib import Path


def get_db() -> sqlite3.Connection:
    from .config import get_config
    path = Path(get_config().db.path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS daily_keys (
            date     TEXT NOT NULL,
            key_code INTEGER NOT NULL,
            key_name TEXT NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, key_code)
        );
        CREATE TABLE IF NOT EXISTS daily_mouse (
            date   TEXT NOT NULL,
            button TEXT NOT NULL,
            count  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, button)
        );
    """)
    conn.commit()


def load_today(conn: sqlite3.Connection) -> dict:
    today = str(date_type.today())
    keys = {
        row["key_name"]: row["count"]
        for row in conn.execute(
            "SELECT key_name, count FROM daily_keys WHERE date = ?", (today,)
        )
    }
    mouse = {
        row["button"]: row["count"]
        for row in conn.execute(
            "SELECT button, count FROM daily_mouse WHERE date = ?", (today,)
        )
    }
    return {"keys": keys, "mouse": mouse}


def flush(
    conn: sqlite3.Connection,
    keys: dict[str, tuple[int, int]],
    mouse: dict[str, int],
    today: str,
) -> None:
    with conn:
        for name, (code, count) in keys.items():
            conn.execute(
                """
                INSERT INTO daily_keys (date, key_code, key_name, count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (date, key_code) DO UPDATE SET count = count + excluded.count
                """,
                (today, code, name, count),
            )
        for button, count in mouse.items():
            conn.execute(
                """
                INSERT INTO daily_mouse (date, button, count)
                VALUES (?, ?, ?)
                ON CONFLICT (date, button) DO UPDATE SET count = count + excluded.count
                """,
                (today, button, count),
            )


def get_top_keys(conn: sqlite3.Connection, date: str, limit: int | None = 15) -> list[dict]:
    if limit is None:
        rows = conn.execute(
            "SELECT key_name, count FROM daily_keys WHERE date = ? ORDER BY count DESC",
            (date,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT key_name, count FROM daily_keys WHERE date = ? ORDER BY count DESC LIMIT ?",
            (date, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_history(conn: sqlite3.Connection, days: int = 14, mode: str = "total") -> list[dict]:
    if mode == "keyboard":
        sql = """
            SELECT date, SUM(count) AS total FROM daily_keys
            GROUP BY date ORDER BY date DESC LIMIT ?
        """
    elif mode == "mouse":
        sql = """
            SELECT date, SUM(count) AS total FROM daily_mouse
            WHERE button NOT IN ('scroll_up', 'scroll_down')
            GROUP BY date ORDER BY date DESC LIMIT ?
        """
    else:
        sql = """
            WITH combined AS (
                SELECT date, count FROM daily_keys
                UNION ALL
                SELECT date, count FROM daily_mouse
                WHERE button NOT IN ('scroll_up', 'scroll_down')
            )
            SELECT date, SUM(count) AS total FROM combined
            GROUP BY date ORDER BY date DESC LIMIT ?
        """
    rows = conn.execute(sql, (days,)).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_lifetime_totals(conn: sqlite3.Connection) -> dict:
    kb = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM daily_keys"
    ).fetchone()[0]
    mouse = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM daily_mouse WHERE button NOT IN ('scroll_up', 'scroll_down')"
    ).fetchone()[0]
    return {"keyboard": kb, "mouse": mouse, "total": kb + mouse}


def get_lifetime_stats(conn: sqlite3.Connection) -> dict:
    totals = get_lifetime_totals(conn)

    row = conn.execute("""
        SELECT MIN(date) AS first_date, COUNT(DISTINCT date) AS active_days
        FROM (SELECT date FROM daily_keys UNION SELECT date FROM daily_mouse)
    """).fetchone()

    record_row = conn.execute("""
        WITH combined AS (
            SELECT date, count FROM daily_keys
            UNION ALL
            SELECT date, count FROM daily_mouse
            WHERE button NOT IN ('scroll_up', 'scroll_down')
        )
        SELECT date, SUM(count) AS total FROM combined
        GROUP BY date ORDER BY total DESC LIMIT 1
    """).fetchone()

    return {
        **totals,
        "first_date": row["first_date"] or str(date_type.today()),
        "active_days": row["active_days"] or 0,
        "record_date": record_row["date"] if record_row else "",
        "record_total": record_row["total"] if record_row else 0,
    }


def get_all_time_top_keys(conn: sqlite3.Connection, limit: int = 20) -> list[tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT key_name, SUM(count) AS total FROM daily_keys
        GROUP BY key_name ORDER BY total DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [(r["key_name"], r["total"]) for r in rows]


def get_week_totals(conn: sqlite3.Connection) -> tuple[int, int]:
    row = conn.execute("""
        WITH combined AS (
            SELECT date, count FROM daily_keys
            UNION ALL
            SELECT date, count FROM daily_mouse
            WHERE button NOT IN ('scroll_up', 'scroll_down')
        ), daily AS (
            SELECT date, SUM(count) AS total FROM combined GROUP BY date
        )
        SELECT
            COALESCE(SUM(CASE WHEN date >= date('now', '-6 days') THEN total ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN date >= date('now', '-13 days') AND date < date('now', '-6 days') THEN total ELSE 0 END), 0)
        FROM daily
    """).fetchone()
    return (row[0], row[1])


def get_day_stats(conn: sqlite3.Connection, date: str, top_limit: int = 15) -> dict:
    kb_total = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM daily_keys WHERE date = ?", (date,)
    ).fetchone()[0]
    top_keys = [(r["key_name"], r["count"]) for r in get_top_keys(conn, date, top_limit)]
    mouse = {
        row["button"]: row["count"]
        for row in conn.execute(
            "SELECT button, count FROM daily_mouse WHERE date = ?", (date,)
        )
    }
    return {"keyboard_total": kb_total, "top_keys": top_keys, "mouse": mouse}
```

- [ ] **Step 6: Run tests — expect all pass**

```bash
uv run pytest tests/test_db.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock tests/ src/tapstats/db.py
git commit -m "feat(db): scroll exclusion, lifetime/week/day queries, history mode param"
```

---

## Task 2: Update daemon.py — lifetime counters + new JSON structure

**Files:**
- Modify: `src/tapstats/daemon.py`
- Create: `tests/test_daemon.py`

Key change: `lifetime_kb_base` = all-time keyboard total minus today's DB-committed portion. Same for mouse. This avoids double-counting today's data between the DB snapshot and the live `today_keys` accumulator.

- [ ] **Step 1: Write failing tests**

Create `tests/test_daemon.py`:

```python
import json
from datetime import date as date_type
from unittest.mock import MagicMock, patch

import pytest

from tapstats.daemon import Daemon


def _make_daemon(tmp_path, today_keys=None, today_mouse=None,
                  lifetime_kb_base=900, lifetime_mouse_base=190):
    """Construct a Daemon with mocked dependencies, no event loop needed."""
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


def test_date_rollover_preserves_lifetime_base(tmp_path):
    d, path = _make_daemon(tmp_path, lifetime_kb_base=5000, lifetime_mouse_base=1000)
    d._today_date = "2026-05-11"

    with patch("tapstats.daemon.date_type") as mock_date, \
         patch.object(d, "_do_flush"), \
         patch.object(d, "_write_runtime"), \
         patch("tapstats.daemon.get_lifetime_totals",
               return_value={"keyboard": 6000, "mouse": 1200, "total": 7200}):
        mock_date.today.return_value.__str__ = lambda _: "2026-05-12"
        d._check_date_rollover()

    # After rollover, base is refreshed from DB (today is now empty so base = full DB total)
    assert d.lifetime_kb_base == 6000
    assert d.lifetime_mouse_base == 1200
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_daemon.py -v 2>&1 | head -40
```

- [ ] **Step 3: Update daemon.py**

Replace `src/tapstats/daemon.py`:

```python
import asyncio
import json
import os
import signal
import subprocess
import time
from collections import defaultdict
from datetime import date as date_type
from pathlib import Path

import evdev
from evdev import InputDevice, ecodes

from .config import get_config
from .db import flush, get_db, get_lifetime_totals, load_today

RUNTIME_JSON = Path(f"/run/user/{os.getuid()}/tapstats.json")

MOUSE_BUTTONS = {
    ecodes.BTN_LEFT: "left",
    ecodes.BTN_RIGHT: "right",
    ecodes.BTN_MIDDLE: "middle",
}


def _key_name(code: int) -> str:
    name = ecodes.KEY.get(code, f"KEY_{code}")
    return name[0] if isinstance(name, list) else name


class Daemon:
    def __init__(self) -> None:
        cfg = get_config()
        self._tick_interval = cfg.daemon.tick_interval
        self._flush_interval = cfg.daemon.flush_interval
        self._waybar_signum = signal.SIGRTMIN + cfg.waybar.signal
        self.db = get_db()

        today_data = load_today(self.db)
        self.today_keys: dict[str, int] = dict(today_data["keys"])
        self.today_mouse: dict[str, int] = dict(today_data["mouse"])
        self.buf_keys: dict[str, tuple[int, int]] = {}
        self.buf_mouse: dict[str, int] = defaultdict(int)
        self._devices: dict[str, InputDevice] = {}
        self._today_date = str(date_type.today())
        self._last_flush = time.monotonic()

        # Lifetime base = all-time DB totals minus today's committed portion,
        # so adding today_keys/today_mouse live totals avoids double-counting.
        lt = get_lifetime_totals(self.db)
        today_kb = sum(today_data["keys"].values())
        today_clicks = sum(
            v for k, v in today_data["mouse"].items()
            if k not in ("scroll_up", "scroll_down")
        )
        self.lifetime_kb_base: int = lt["keyboard"] - today_kb
        self.lifetime_mouse_base: int = lt["mouse"] - today_clicks

    def _find_devices(self) -> list[InputDevice]:
        devices = []
        for path in evdev.list_devices():
            try:
                dev = InputDevice(path)
                if ecodes.EV_KEY in dev.capabilities():
                    devices.append(dev)
            except OSError:
                pass
        return devices

    async def _handle_device(self, dev: InputDevice) -> None:
        try:
            async for event in dev.async_read_loop():
                if event.type == ecodes.EV_KEY:
                    ev = evdev.categorize(event)
                    if ev.keystate != evdev.KeyEvent.key_down:
                        continue
                    code = event.code
                    if code in MOUSE_BUTTONS:
                        btn = MOUSE_BUTTONS[code]
                        self.today_mouse[btn] = self.today_mouse.get(btn, 0) + 1
                        self.buf_mouse[btn] += 1
                    else:
                        name = _key_name(code)
                        self.today_keys[name] = self.today_keys.get(name, 0) + 1
                        prev = self.buf_keys.get(name, (code, 0))
                        self.buf_keys[name] = (code, prev[1] + 1)
                elif event.type == ecodes.EV_REL and event.code == ecodes.REL_WHEEL:
                    btn = "scroll_up" if event.value > 0 else "scroll_down"
                    delta = abs(event.value)
                    self.today_mouse[btn] = self.today_mouse.get(btn, 0) + delta
                    self.buf_mouse[btn] += delta
        except (OSError, IOError):
            pass
        finally:
            self._devices.pop(dev.path, None)

    def _write_runtime(self) -> None:
        top = sorted(self.today_keys.items(), key=lambda x: x[1], reverse=True)[:10]
        kb_today = sum(self.today_keys.values())
        mouse_today = self.today_mouse
        clicks_today = (
            mouse_today.get("left", 0)
            + mouse_today.get("right", 0)
            + mouse_today.get("middle", 0)
        )
        lifetime_kb = self.lifetime_kb_base + kb_today
        lifetime_mouse = self.lifetime_mouse_base + clicks_today
        data = {
            "today": {
                "date": self._today_date,
                "keyboard": {"total": kb_today, "top": top},
                "mouse": dict(mouse_today),
            },
            "lifetime": {
                "keyboard": lifetime_kb,
                "mouse": lifetime_mouse,
                "total": lifetime_kb + lifetime_mouse,
            },
        }
        tmp = RUNTIME_JSON.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.rename(RUNTIME_JSON)

    def _signal_waybar(self) -> None:
        subprocess.run(["pkill", f"-{self._waybar_signum}", "waybar"], capture_output=True)

    def _do_flush(self) -> None:
        if self.buf_keys or self.buf_mouse:
            flush(self.db, self.buf_keys, dict(self.buf_mouse), self._today_date)
            self.buf_keys.clear()
            self.buf_mouse.clear()
        self._last_flush = time.monotonic()

    def _check_date_rollover(self) -> None:
        today = str(date_type.today())
        if today != self._today_date:
            self._do_flush()
            self.today_keys.clear()
            self.today_mouse.clear()
            self._today_date = today
            # Refresh lifetime base: today is empty so base = full DB total
            lt = get_lifetime_totals(self.db)
            self.lifetime_kb_base = lt["keyboard"]
            self.lifetime_mouse_base = lt["mouse"]

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(self._tick_interval)
            self._check_date_rollover()
            self._write_runtime()
            self._signal_waybar()
            if time.monotonic() - self._last_flush >= self._flush_interval:
                self._do_flush()

    async def _watch_devices(self) -> None:
        while True:
            for dev in self._find_devices():
                if dev.path not in self._devices:
                    self._devices[dev.path] = dev
                    asyncio.create_task(self._handle_device(dev))
            await asyncio.sleep(5.0)

    async def run(self) -> None:
        await asyncio.gather(self._tick(), self._watch_devices())


def main() -> None:
    asyncio.run(Daemon().run())
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/test_daemon.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/tapstats/daemon.py tests/test_daemon.py
git commit -m "feat(daemon): lifetime counters and restructured runtime JSON"
```

---

## Task 3: Update waybar.py + config.py

**Files:**
- Modify: `src/tapstats/waybar.py`
- Modify: `src/tapstats/config.py`
- Create: `tests/test_waybar.py`

Key changes: read paths `data["keyboard"]` → `data["today"]["keyboard"]`; extract pure `_format_output` helper; add `"total"` display mode; tooltip shows lifetime total.

- [ ] **Step 1: Write failing tests**

Create `tests/test_waybar.py`:

```python
import json
from datetime import date as date_type
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_waybar.py -v 2>&1 | head -30
```

- [ ] **Step 3: Rewrite waybar.py**

Replace `src/tapstats/waybar.py`:

```python
import json
import os
from datetime import date as date_type
from pathlib import Path

from .config import get_config

RUNTIME_JSON = Path(f"/run/user/{os.getuid()}/tapstats.json")
_FALLBACK = json.dumps({"text": "󰌌 —", "tooltip": "tapstats not running"})


def _fmt(n: int) -> str:
    if n >= 1000:
        v = n / 1000
        return f"{v:.1f}k" if v % 1 else f"{int(v)}k"
    return str(n)


def _format_output(data: dict, cfg) -> str | None:
    today = data.get("today", {})
    if today.get("date") != str(date_type.today()):
        return None

    kb = today.get("keyboard", {}).get("total", 0)
    mouse = today.get("mouse", {})
    clicks = mouse.get("left", 0) + mouse.get("right", 0) + mouse.get("middle", 0)
    lifetime_total = data.get("lifetime", {}).get("total", 0)

    fmt = _fmt if cfg.waybar.compact else lambda n: f"{n:,}"

    match cfg.waybar.display:
        case "total":
            text = f"󰌌 󰍽 {fmt(kb + clicks)}"
        case "both":
            text = f"󰌌 {fmt(kb)}  󰍽 {fmt(clicks)}"
        case "mouse":
            text = f"󰍽 {fmt(clicks)}"
        case _:
            text = f"󰌌 {fmt(kb)}"

    n = cfg.waybar.top_keys_count
    top_lines = "\n".join(
        f"  {name.replace('KEY_', ''):<10} {count:,}"
        for name, count in today.get("keyboard", {}).get("top", [])[:n]
    )

    tooltip = (
        f"TAPSTATS  {today['date']}\n\n"
        f"KEYBOARD  {kb:,}\n"
        f"{top_lines}\n\n"
        f"MOUSE\n"
        f"  Left {mouse.get('left', 0):,}  Right {mouse.get('right', 0):,}  Middle {mouse.get('middle', 0):,}\n"
        f"  Scroll ↑ {mouse.get('scroll_up', 0):,}  ↓ {mouse.get('scroll_down', 0):,}\n\n"
        f"LIFETIME  {lifetime_total:,}"
    )

    return json.dumps({"text": text, "tooltip": tooltip})


def main() -> None:
    if not RUNTIME_JSON.exists():
        print(_FALLBACK)
        return
    try:
        data = json.loads(RUNTIME_JSON.read_text())
    except Exception:
        print(_FALLBACK)
        return

    cfg = get_config()
    result = _format_output(data, cfg)
    print(result if result is not None else _FALLBACK)
```

- [ ] **Step 4: Update config.py — change display default**

In `src/tapstats/config.py`, change line:

```python
    display: str = "keyboard"  # "keyboard", "mouse", "both"
```

to:

```python
    display: str = "total"  # "keyboard", "mouse", "both", "total"
```

- [ ] **Step 5: Run tests — expect all pass**

```bash
uv run pytest tests/test_waybar.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/tapstats/waybar.py src/tapstats/config.py tests/test_waybar.py
git commit -m "feat(waybar): total display mode, updated JSON read paths, lifetime tooltip"
```

---

## Task 4: panel.py — scaffold, constants, TODAY tab

**Files:**
- Modify: `src/tapstats/panel.py` (full rewrite begins here)
- Create: `tests/test_panel_helpers.py`

This task establishes the app skeleton (ContentSwitcher, TabBar, keybindings) and implements the TODAY tab with `TodayView`, `TodayHeader`, `TodayKeyboard`, `TodayMouse`. The KEYS, HISTORY, LIFETIME panes are stubbed with placeholder `Static` widgets.

- [ ] **Step 1: Write tests for helper functions**

Create `tests/test_panel_helpers.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_panel_helpers.py -v 2>&1 | head -20
```

- [ ] **Step 3: Write the new panel.py (scaffold + TODAY)**

Replace `src/tapstats/panel.py` entirely:

```python
import json
import os
from datetime import date as date_type, timedelta
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ContentSwitcher, Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Footer, ListItem, ListView, Static

from .config import get_config
from .db import (
    get_all_time_top_keys,
    get_db,
    get_day_stats,
    get_history,
    get_lifetime_stats,
    get_top_keys,
    get_week_totals,
)

RUNTIME_JSON = Path(f"/run/user/{os.getuid()}/tapstats.json")
SPARK = " ▁▂▃▄▅▆▇█"

HEAT_BG = [
    "#1c2128", "#1a3a2a", "#1e4a30", "#1d5c35",
    "#2d7a45", "#3a9e58", "#52c06a", "#76e088", "#9eff9e",
]
HEAT_FG = [
    "#3a4050", "#5a8a6a", "#7ab88a", "#8dd4a0",
    "#a8e8bc", "#c0f0d0", "#e0ffe8", "#ffffff", "#0d3320",
]
BAR_COLORS = ["#9ece6a", "#7aa2f7", "#bb9af7", "#ff9e64", "#f7768e", "#7dcfff", "#e0af68", "#2ac3de"]

# (db_key_name, display_label, cell_width_chars)
# None = visual gap between key groups
QWERTY_LAYOUT: list[list[tuple[str, str, int] | None]] = [
    [
        ("KEY_ESC", "ESC", 5), None,
        ("KEY_F1", "F1", 4), ("KEY_F2", "F2", 4), ("KEY_F3", "F3", 4), ("KEY_F4", "F4", 4), None,
        ("KEY_F5", "F5", 4), ("KEY_F6", "F6", 4), ("KEY_F7", "F7", 4), ("KEY_F8", "F8", 4), None,
        ("KEY_F9", "F9", 4), ("KEY_F10", "F10", 4), ("KEY_F11", "F11", 4), ("KEY_F12", "F12", 4),
    ],
    [
        ("KEY_GRAVE", "`", 4), ("KEY_1", "1", 4), ("KEY_2", "2", 4), ("KEY_3", "3", 4),
        ("KEY_4", "4", 4), ("KEY_5", "5", 4), ("KEY_6", "6", 4), ("KEY_7", "7", 4),
        ("KEY_8", "8", 4), ("KEY_9", "9", 4), ("KEY_0", "0", 4), ("KEY_MINUS", "-", 4),
        ("KEY_EQUAL", "=", 4), ("KEY_BACKSPACE", "BKSP", 6),
    ],
    [
        ("KEY_TAB", "TAB", 6), ("KEY_Q", "Q", 4), ("KEY_W", "W", 4), ("KEY_E", "E", 4),
        ("KEY_R", "R", 4), ("KEY_T", "T", 4), ("KEY_Y", "Y", 4), ("KEY_U", "U", 4),
        ("KEY_I", "I", 4), ("KEY_O", "O", 4), ("KEY_P", "P", 4), ("KEY_LEFTBRACE", "[", 4),
        ("KEY_RIGHTBRACE", "]", 4), ("KEY_BACKSLASH", "\\", 4),
    ],
    [
        ("KEY_CAPSLOCK", "CAPS", 7), ("KEY_A", "A", 4), ("KEY_S", "S", 4), ("KEY_D", "D", 4),
        ("KEY_F", "F", 4), ("KEY_G", "G", 4), ("KEY_H", "H", 4), ("KEY_J", "J", 4),
        ("KEY_K", "K", 4), ("KEY_L", "L", 4), ("KEY_SEMICOLON", ";", 4), ("KEY_APOSTROPHE", "'", 4),
        ("KEY_ENTER", "RET", 7),
    ],
    [
        ("KEY_LEFTSHIFT", "SHFT", 9), ("KEY_Z", "Z", 4), ("KEY_X", "X", 4), ("KEY_C", "C", 4),
        ("KEY_V", "V", 4), ("KEY_B", "B", 4), ("KEY_N", "N", 4), ("KEY_M", "M", 4),
        ("KEY_COMMA", ",", 4), ("KEY_DOT", ".", 4), ("KEY_SLASH", "/", 4),
        ("KEY_RIGHTSHIFT", "SHFT", 9),
    ],
    [
        ("KEY_LEFTCTRL", "CTL", 5), ("KEY_LEFTMETA", "SYS", 4), ("KEY_LEFTALT", "ALT", 5),
        ("KEY_SPACE", "SPACE", 22), ("KEY_RIGHTALT", "ALT", 5), ("KEY_RIGHTMETA", "SYS", 4),
        ("KEY_COMPOSE", "MNU", 4), ("KEY_RIGHTCTRL", "CTL", 5),
    ],
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _heat_level(value: int, max_val: int) -> int:
    if max_val == 0 or value == 0:
        return 0
    return min(8, round(value / max_val * 8))


def _bar(value: int, max_val: int, width: int = 24) -> str:
    if max_val == 0:
        return " " * width
    filled = round(value / max_val * width)
    return "█" * filled + " " * (width - filled)


def _spark_char(value: int, max_val: int) -> str:
    if max_val == 0:
        return SPARK[0]
    return SPARK[min(8, round(value / max_val * 8))]


def _compact(n: int) -> str:
    if n >= 1000:
        v = n / 1000
        return f"{v:.1f}k" if v % 1 else f"{int(v)}k"
    return str(n)


# ── messages ─────────────────────────────────────────────────────────────────

class DrillDown(Message):
    def __init__(self, date: str) -> None:
        self.date = date
        super().__init__()


class DrillDownExit(Message):
    pass


# ── tab bar ──────────────────────────────────────────────────────────────────

class TabBar(Static):
    active: reactive[str] = reactive("today")

    _TABS = [
        ("today",    "1 TODAY"),
        ("keys",     "2 KEYS"),
        ("history",  "3 HISTORY"),
        ("lifetime", "4 LIFETIME"),
    ]

    def render(self) -> str:
        parts = []
        for key, label in self._TABS:
            if key == self.active:
                parts.append(f"[reverse bold] {label} [/reverse bold]")
            else:
                parts.append(f"[dim] {label} [/dim]")
        return "  ".join(parts)


# ── today tab ────────────────────────────────────────────────────────────────

class TodayHeader(Static):
    keyboard_total: reactive[int] = reactive(0)
    clicks: reactive[int] = reactive(0)
    date: reactive[str] = reactive("")
    pinned: reactive[bool] = reactive(False)

    def render(self) -> str:
        total = self.keyboard_total + self.clicks
        date_tag = f" [dim](pinned: {self.date}  Esc to return)[/dim]" if self.pinned else f" [dim]{self.date}[/dim]"
        return (
            f"[bold]TOTAL ACTIONS[/bold]{date_tag}\n"
            f"[bold green]{total:,}[/bold green]\n"
            f"[dim]󰌌 {self.keyboard_total:,}  󰍽 {self.clicks:,}[/dim]"
        )


class TodayKeyboard(Static):
    keyboard_total: reactive[int] = reactive(0)
    top_keys: reactive[list] = reactive([])

    def render(self) -> str:
        if not self.top_keys:
            return f"[bold]KEYBOARD[/bold]  [green]{self.keyboard_total:,}[/green]\n\n[dim]No data[/dim]"
        max_count = self.top_keys[0][1] if self.top_keys else 1
        lines = [f"[bold]KEYBOARD[/bold]  [green]{self.keyboard_total:,}[/green]\n"]
        for i, (name, count) in enumerate(self.top_keys[:5]):
            label = name.replace("KEY_", "")[:10]
            color = BAR_COLORS[i % len(BAR_COLORS)]
            bar = _bar(count, max_count, 14)
            lines.append(f"[dim]{label:<10}[/dim]  [{color}]{bar}[/{color}]")
        return "\n".join(lines)


class TodayMouse(Static):
    mouse: reactive[dict] = reactive({})

    def render(self) -> str:
        m = self.mouse
        clicks = m.get("left", 0) + m.get("right", 0) + m.get("middle", 0)
        scroll = m.get("scroll_up", 0) + m.get("scroll_down", 0)
        return (
            f"[bold]MOUSE CLICKS[/bold]  [blue]{clicks:,}[/blue]\n\n"
            f"[dim]Left   [/dim][blue]{m.get('left', 0):>8,}[/blue]\n"
            f"[dim]Right  [/dim][blue]{m.get('right', 0):>8,}[/blue]\n"
            f"[dim]Middle [/dim][blue]{m.get('middle', 0):>8,}[/blue]\n\n"
            f"[dim]Scroll [/dim][#bb9af7]±{scroll:,} lines[/#bb9af7]\n"
            f"[dim](not counted in total)[/dim]"
        )


class TodayView(Static):
    BINDINGS = [Binding("escape", "exit_pin", "Back", show=False)]

    keyboard_total: reactive[int] = reactive(0)
    top_keys: reactive[list] = reactive([])
    mouse: reactive[dict] = reactive({})
    pinned_date: reactive[str | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield TodayHeader(id="today-header")
        with Horizontal(id="today-cols"):
            yield TodayKeyboard(id="today-kb")
            yield TodayMouse(id="today-mouse")

    def watch_keyboard_total(self, v: int) -> None:
        self.query_one(TodayHeader).keyboard_total = v
        self.query_one(TodayKeyboard).keyboard_total = v

    def watch_top_keys(self, v: list) -> None:
        self.query_one(TodayKeyboard).top_keys = v

    def watch_mouse(self, v: dict) -> None:
        clicks = v.get("left", 0) + v.get("right", 0) + v.get("middle", 0)
        h = self.query_one(TodayHeader)
        h.clicks = clicks
        h.date = self.pinned_date or str(date_type.today())
        h.pinned = self.pinned_date is not None
        self.query_one(TodayMouse).mouse = v

    def watch_pinned_date(self, v: str | None) -> None:
        h = self.query_one(TodayHeader)
        h.date = v or str(date_type.today())
        h.pinned = v is not None

    def action_exit_pin(self) -> None:
        if self.pinned_date is not None:
            self.pinned_date = None
            self.post_message(DrillDownExit())


# ── stub panes (filled in Tasks 5-7) ─────────────────────────────────────────

class KeysView(Static):
    def render(self) -> str:
        return "[dim]KEYS — coming in Task 5[/dim]"


class HistoryView(Static):
    def render(self) -> str:
        return "[dim]HISTORY — coming in Task 6[/dim]"


class LifetimeView(Static):
    def render(self) -> str:
        return "[dim]LIFETIME — coming in Task 7[/dim]"


# ── app ───────────────────────────────────────────────────────────────────────

class TapStatsApp(App):
    TITLE = "tapstats"
    CSS = """
    Screen {
        background: $surface;
    }
    TabBar {
        height: 1;
        background: $surface;
        padding: 0 1;
        dock: top;
    }
    ContentSwitcher {
        height: 1fr;
    }
    TodayView {
        height: 100%;
        padding: 1 2;
    }
    TodayHeader {
        height: 5;
        border-bottom: solid $accent-darken-1;
        margin-bottom: 1;
    }
    #today-cols {
        height: 1fr;
    }
    TodayKeyboard {
        width: 1fr;
        padding-right: 2;
        border-right: solid $accent-darken-1;
    }
    TodayMouse {
        width: 30;
        padding-left: 2;
    }
    KeysView, HistoryView, LifetimeView {
        height: 100%;
        padding: 1 2;
    }
    Footer {
        background: $surface;
        color: $text-muted;
    }
    """
    BINDINGS = [
        Binding("1", "switch_tab('today')",    "Today",    show=False),
        Binding("2", "switch_tab('keys')",     "Keys",     show=False),
        Binding("3", "switch_tab('history')",  "History",  show=False),
        Binding("4", "switch_tab('lifetime')", "Lifetime", show=False),
        Binding("tab", "next_tab",             "Next tab", show=False),
        Binding("q", "quit",                   "Quit"),
        Binding("r", "refresh",                "Refresh"),
    ]

    _TAB_ORDER = ["today", "keys", "history", "lifetime"]

    def compose(self) -> ComposeResult:
        yield TabBar()
        with ContentSwitcher(initial="today"):
            yield TodayView(id="today")
            yield KeysView(id="keys")
            yield HistoryView(id="history")
            yield LifetimeView(id="lifetime")
        yield Footer()

    def on_mount(self) -> None:
        self.db = get_db()
        self.action_refresh()
        self.set_interval(5.0, self.action_refresh)

    def _switch_tab(self, tab: str) -> None:
        self.query_one(ContentSwitcher).current = tab
        self.query_one(TabBar).active = tab

    def action_switch_tab(self, tab: str) -> None:
        self._switch_tab(tab)

    def action_next_tab(self) -> None:
        current = self.query_one(ContentSwitcher).current
        idx = self._TAB_ORDER.index(current) if current in self._TAB_ORDER else 0
        self._switch_tab(self._TAB_ORDER[(idx + 1) % len(self._TAB_ORDER)])

    def action_refresh(self) -> None:
        cfg = get_config()
        today = str(date_type.today())
        today_view = self.query_one(TodayView)

        if today_view.pinned_date:
            stats = get_day_stats(self.db, today_view.pinned_date)
            today_view.keyboard_total = stats["keyboard_total"]
            today_view.top_keys = stats["top_keys"]
            today_view.mouse = stats["mouse"]
            return

        # Try runtime JSON first (live data)
        if RUNTIME_JSON.exists():
            try:
                data = json.loads(RUNTIME_JSON.read_text())
                td = data.get("today", {})
                if td.get("date") == today:
                    today_view.keyboard_total = td["keyboard"]["total"]
                    today_view.top_keys = [(n, c) for n, c in td["keyboard"]["top"]]
                    today_view.mouse = td["mouse"]
                    return
            except Exception:
                pass

        # Fall back to DB
        stats = get_day_stats(self.db, today)
        today_view.keyboard_total = stats["keyboard_total"]
        today_view.top_keys = stats["top_keys"]
        today_view.mouse = stats["mouse"]

    def on_drill_down(self, message: DrillDown) -> None:
        today_view = self.query_one(TodayView)
        today_view.pinned_date = message.date
        self._switch_tab("today")
        self.action_refresh()

    def on_drill_down_exit(self, _: DrillDownExit) -> None:
        self._switch_tab("history")


def main() -> None:
    TapStatsApp().run()
```

- [ ] **Step 4: Run helper tests — expect all pass**

```bash
uv run pytest tests/test_panel_helpers.py -v
```

- [ ] **Step 5: Smoke test the TUI visually**

```bash
uv run tapstats
```

Expected: TUI opens, shows TODAY tab with keyboard and mouse columns. Tab / 1-4 switches panes. `r` refreshes. `q` quits. Other tabs show placeholder text.

- [ ] **Step 6: Commit**

```bash
git add src/tapstats/panel.py tests/test_panel_helpers.py
git commit -m "feat(panel): scaffold 4-tab app with TODAY view and stubs for remaining tabs"
```

---

## Task 5: panel.py — KEYS tab

**Files:**
- Modify: `src/tapstats/panel.py`

Replace the `KeysView` stub with a full implementation. The view renders the QWERTY heatmap by default; pressing `b` switches to a colored ranked bar chart; `h` switches back. `←` / `→` navigate to previous / next day.

- [ ] **Step 1: Replace KeysView stub in panel.py**

Remove the stub `KeysView` class and add these classes before the `TapStatsApp` class:

```python
class KeyboardHeatmap(Static):
    key_data: reactive[dict] = reactive({})

    def render(self) -> Text:
        data = self.key_data
        max_count = max(data.values(), default=1) if data else 1
        text = Text()
        for row in QWERTY_LAYOUT:
            for key in row:
                if key is None:
                    text.append(" ")
                    continue
                name, label, width = key
                count = data.get(name, 0)
                level = _heat_level(count, max_count)
                bg = HEAT_BG[level]
                fg = HEAT_FG[level]
                cell = label.center(width - 2)
                text.append(f" {cell} ", style=Style(bgcolor=bg, color=fg))
            text.append("\n")
        # Legend
        text.append("\n")
        text.append("low ", style="dim")
        for i, bg in enumerate(HEAT_BG):
            text.append("  ", style=Style(bgcolor=bg))
        text.append(" high", style="dim")
        return text


class KeysBars(Static):
    key_data: reactive[dict] = reactive({})

    def render(self) -> str:
        if not self.key_data:
            return "[dim]No data[/dim]"
        items = sorted(self.key_data.items(), key=lambda x: x[1], reverse=True)
        max_count = items[0][1] if items else 1
        lines = []
        for i, (name, count) in enumerate(items):
            color = BAR_COLORS[i % len(BAR_COLORS)]
            label = name.replace("KEY_", "")[:12]
            bar = _bar(count, max_count, 22)
            lines.append(f"[{color}]{label:<12}[/{color}]  [{color}]{bar}[/{color}]  [dim]{count:,}[/dim]")
        return "\n".join(lines)


class KeysView(Static):
    BINDINGS = [
        Binding("h", "mode_heatmap", "Heatmap", show=True),
        Binding("b", "mode_bars",    "Bars",    show=True),
        Binding("left",  "prev_day", "Prev day", show=False),
        Binding("right", "next_day", "Next day", show=False),
    ]

    view_date: reactive[str] = reactive("")
    mode: reactive[str] = reactive("heatmap")
    key_data: reactive[dict] = reactive({})

    def compose(self) -> ComposeResult:
        yield Static(id="keys-header")
        with ContentSwitcher(initial="keys-heatmap"):
            yield KeyboardHeatmap(id="keys-heatmap")
            yield KeysBars(id="keys-bars")

    def on_mount(self) -> None:
        self.view_date = str(date_type.today())

    def watch_view_date(self, _: str) -> None:
        self._load_data()

    def watch_key_data(self, v: dict) -> None:
        self.query_one(KeyboardHeatmap).key_data = v
        self.query_one(KeysBars).key_data = v

    def watch_mode(self, v: str) -> None:
        switcher = self.query_one(ContentSwitcher)
        switcher.current = "keys-heatmap" if v == "heatmap" else "keys-bars"
        self._update_header()

    def _load_data(self) -> None:
        rows = get_top_keys(self.app.db, self.view_date, limit=None)  # type: ignore[attr-defined]
        self.key_data = {r["key_name"]: r["count"] for r in rows}
        self._update_header()

    def _update_header(self) -> None:
        mode_label = "heatmap (b: bars)" if self.mode == "heatmap" else "bars (h: heatmap)"
        is_today = self.view_date == str(date_type.today())
        date_label = "today" if is_today else self.view_date
        self.query_one("#keys-header", Static).update(
            f"[bold]KEYS[/bold]  [dim]{date_label}  ←/→ navigate days  {mode_label}[/dim]"
        )

    def action_mode_heatmap(self) -> None:
        self.mode = "heatmap"

    def action_mode_bars(self) -> None:
        self.mode = "bars"

    def action_prev_day(self) -> None:
        d = date_type.fromisoformat(self.view_date) - timedelta(days=1)
        self.view_date = str(d)

    def action_next_day(self) -> None:
        d = date_type.fromisoformat(self.view_date) + timedelta(days=1)
        if d <= date_type.today():
            self.view_date = str(d)
```

Also add `KeysView` CSS inside `TapStatsApp.CSS`:

```css
    KeysView {
        height: 100%;
        padding: 1 2;
    }
    #keys-header {
        height: 1;
        margin-bottom: 1;
    }
    KeyboardHeatmap {
        height: auto;
    }
    KeysBars {
        height: 1fr;
        overflow-y: auto;
    }
```

Also update `action_refresh` in `TapStatsApp` to refresh the KeysView when it is the active tab:

```python
    def action_refresh(self) -> None:
        cfg = get_config()
        today = str(date_type.today())
        today_view = self.query_one(TodayView)

        # Refresh KEYS if active
        current = self.query_one(ContentSwitcher).current
        if current == "keys":
            self.query_one(KeysView)._load_data()

        if today_view.pinned_date:
            stats = get_day_stats(self.db, today_view.pinned_date)
            today_view.keyboard_total = stats["keyboard_total"]
            today_view.top_keys = stats["top_keys"]
            today_view.mouse = stats["mouse"]
            return

        if RUNTIME_JSON.exists():
            try:
                data = json.loads(RUNTIME_JSON.read_text())
                td = data.get("today", {})
                if td.get("date") == today:
                    today_view.keyboard_total = td["keyboard"]["total"]
                    today_view.top_keys = [(n, c) for n, c in td["keyboard"]["top"]]
                    today_view.mouse = td["mouse"]
                    return
            except Exception:
                pass

        stats = get_day_stats(self.db, today)
        today_view.keyboard_total = stats["keyboard_total"]
        today_view.top_keys = stats["top_keys"]
        today_view.mouse = stats["mouse"]
```

- [ ] **Step 2: Smoke test KEYS tab**

```bash
uv run tapstats
```

Press `2` — KEYS tab should show the heatmap. Press `b` — switches to bars. Press `h` — back to heatmap. Press `←` — goes to yesterday's data. Check that header updates with the date.

- [ ] **Step 3: Commit**

```bash
git add src/tapstats/panel.py
git commit -m "feat(panel): KEYS tab with heatmap and colored bar chart, day navigation"
```

---

## Task 6: panel.py — HISTORY tab

**Files:**
- Modify: `src/tapstats/panel.py`

Replace the `HistoryView` stub. The view shows a sparkline header, a `ListView` of per-day rows, and a week-vs-week footer. Pressing `Enter` on a row triggers drill-down to that day in the TODAY tab.

- [ ] **Step 1: Replace HistoryView stub in panel.py**

Add these classes before `TapStatsApp`:

```python
class HistoryItem(ListItem):
    def __init__(self, row: dict, color: str, max_val: int) -> None:
        super().__init__()
        self._row = row
        self._color = color
        self._max_val = max_val

    def compose(self) -> ComposeResult:
        bar = _bar(self._row["total"], self._max_val, 28)
        text = (
            f"[dim]{self._row['date']}[/dim]  "
            f"[{self._color}]{bar}[/{self._color}]  "
            f"{self._row['total']:,}"
        )
        yield Static(text)


class HistoryView(Static):
    BINDINGS = [
        Binding("enter", "drill_down", "Drill down", show=True),
        Binding("k", "mode_keyboard", "Keyboard", show=False),
        Binding("m", "mode_mouse",    "Mouse",    show=False),
        Binding("t", "mode_total",    "Total",    show=False),
    ]

    history: reactive[list] = reactive([])
    mode: reactive[str] = reactive("total")
    this_week: reactive[int] = reactive(0)
    last_week: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static(id="history-spark")
        yield ListView(id="history-list")
        yield Static(id="history-footer")

    def watch_history(self, rows: list) -> None:
        self._rebuild_list(rows)
        self._update_spark(rows)

    def watch_mode(self, _: str) -> None:
        self._update_footer()

    def watch_this_week(self, _: int) -> None:
        self._update_footer()

    def watch_last_week(self, _: int) -> None:
        self._update_footer()

    def _rebuild_list(self, rows: list) -> None:
        lv = self.query_one(ListView)
        lv.clear()
        displayed = list(reversed(rows))
        max_val = max((r["total"] for r in displayed), default=1)
        for i, row in enumerate(displayed):
            color = BAR_COLORS[i % len(BAR_COLORS)]
            lv.append(HistoryItem(row, color, max_val))

    def _update_spark(self, rows: list) -> None:
        max_val = max((r["total"] for r in rows), default=1)
        spark = "".join(_spark_char(r["total"], max_val) for r in rows)
        mode_hint = "k: keyboard  m: mouse  t: total"
        self.query_one("#history-spark", Static).update(
            f"[bold]{len(rows)} DAYS[/bold]  [green]{spark}[/green]  [dim]{mode_hint}[/dim]"
        )

    def _update_footer(self) -> None:
        if self.last_week == 0:
            delta_str = ""
        else:
            delta = (self.this_week - self.last_week) / self.last_week * 100
            sign = "+" if delta >= 0 else ""
            delta_str = f"  [dim]{sign}{delta:.1f}% vs last 7d[/dim]"
        mode_label = {"keyboard": "󰌌 keys", "mouse": "󰍽 clicks", "total": "total"}.get(self.mode, "total")
        self.query_one("#history-footer", Static).update(
            f"[dim]This 7d[/dim]  [green]{self.this_week:,}[/green]  "
            f"[dim]Prev 7d[/dim]  [blue]{self.last_week:,}[/blue]{delta_str}  "
            f"[dim]({mode_label})[/dim]"
        )

    def action_drill_down(self) -> None:
        lv = self.query_one(ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, HistoryItem):
            self.post_message(DrillDown(lv.highlighted_child._row["date"]))

    def action_mode_keyboard(self) -> None:
        self.mode = "keyboard"
        self.app.action_refresh()  # type: ignore[attr-defined]

    def action_mode_mouse(self) -> None:
        self.mode = "mouse"
        self.app.action_refresh()  # type: ignore[attr-defined]

    def action_mode_total(self) -> None:
        self.mode = "total"
        self.app.action_refresh()  # type: ignore[attr-defined]
```

Add CSS for `HistoryView` inside `TapStatsApp.CSS`:

```css
    HistoryView {
        height: 100%;
        padding: 1 2;
    }
    #history-spark {
        height: 1;
        margin-bottom: 1;
    }
    #history-list {
        height: 1fr;
        border: none;
    }
    #history-footer {
        height: 1;
        margin-top: 1;
        border-top: solid $accent-darken-1;
        padding-top: 1;
    }
    HistoryItem {
        padding: 0 0;
        height: 1;
    }
    HistoryItem.--highlight {
        background: $accent-darken-2;
    }
```

Update `action_refresh` in `TapStatsApp` to load history:

Add after the `if current == "keys":` block:

```python
        if current == "history" or True:  # always keep history fresh
            hist_view = self.query_one(HistoryView)
            hist_view.history = get_history(self.db, cfg.panel.history_days, hist_view.mode)
            tw, lw = get_week_totals(self.db)
            hist_view.this_week = tw
            hist_view.last_week = lw
```

- [ ] **Step 2: Smoke test HISTORY tab**

```bash
uv run tapstats
```

Press `3` — HISTORY tab shows sparkline, per-day bars, week footer. `↑`/`↓` move cursor. Press `Enter` on a row — switches to TODAY tab showing that day's data. Press `Escape` — returns to HISTORY. Press `k`/`m`/`t` to change mode.

- [ ] **Step 3: Commit**

```bash
git add src/tapstats/panel.py
git commit -m "feat(panel): HISTORY tab with cursor navigation, drill-down, and week comparison"
```

---

## Task 7: panel.py — LIFETIME tab

**Files:**
- Modify: `src/tapstats/panel.py`

Replace the `LifetimeView` stub with the full implementation showing cumulative total, all-time top keys bar chart, and stats panel.

- [ ] **Step 1: Replace LifetimeView stub in panel.py**

Add this class before `TapStatsApp`:

```python
class LifetimeView(Static):
    stats: reactive[dict] = reactive({})
    top_keys: reactive[list] = reactive([])

    def compose(self) -> ComposeResult:
        yield Static(id="lifetime-header")
        with Horizontal(id="lifetime-cols"):
            yield Static(id="lifetime-bars")
            yield Static(id="lifetime-stats")

    def watch_stats(self, v: dict) -> None:
        self._update_header(v)
        self._update_stats(v)

    def watch_top_keys(self, v: list) -> None:
        self._update_bars(v)

    def _update_header(self, v: dict) -> None:
        total = v.get("total", 0)
        kb = v.get("keyboard", 0)
        mouse = v.get("mouse", 0)
        first = v.get("first_date", "")
        days = v.get("active_days", 0)
        self.query_one("#lifetime-header", Static).update(
            f"[bold]ALL-TIME TOTAL ACTIONS[/bold]  [dim]since {first}[/dim]\n"
            f"[bold #ff9e64]{total:,}[/bold #ff9e64]\n"
            f"[dim]󰌌 {kb:,}  󰍽 {mouse:,}  ({days} active days)[/dim]"
        )

    def _update_bars(self, keys: list) -> None:
        if not keys:
            self.query_one("#lifetime-bars", Static).update("[dim]No data[/dim]")
            return
        max_count = keys[0][1] if keys else 1
        lines = ["[bold]ALL-TIME TOP KEYS[/bold]\n"]
        for i, (name, count) in enumerate(keys):
            color = BAR_COLORS[i % len(BAR_COLORS)]
            label = name.replace("KEY_", "")[:12]
            bar = _bar(count, max_count, 22)
            lines.append(f"[{color}]{label:<12}[/{color}]  [{color}]{bar}[/{color}]  [dim]{count:,}[/dim]")
        self.query_one("#lifetime-bars", Static).update("\n".join(lines))

    def _update_stats(self, v: dict) -> None:
        total = v.get("total", 0)
        days = v.get("active_days", 0)
        daily_avg = total // days if days else 0
        record_total = v.get("record_total", 0)
        record_date = v.get("record_date", "—")
        self.query_one("#lifetime-stats", Static).update(
            f"[bold]STATS[/bold]\n\n"
            f"[dim]Active days[/dim]   [green]{days:,}[/green]\n"
            f"[dim]Daily avg  [/dim]   [green]{daily_avg:,}[/green]\n\n"
            f"[dim]Record day [/dim]   [#ff9e64]{record_total:,}[/#ff9e64]\n"
            f"[dim]           [/dim]   [dim]{record_date}[/dim]"
        )
```

Add CSS for `LifetimeView` inside `TapStatsApp.CSS`:

```css
    LifetimeView {
        height: 100%;
        padding: 1 2;
    }
    #lifetime-header {
        height: 5;
        border-bottom: solid $accent-darken-1;
        margin-bottom: 1;
    }
    #lifetime-cols {
        height: 1fr;
    }
    #lifetime-bars {
        width: 1fr;
        padding-right: 2;
        border-right: solid $accent-darken-1;
        overflow-y: auto;
    }
    #lifetime-stats {
        width: 30;
        padding-left: 2;
    }
```

Update `action_refresh` in `TapStatsApp` to load lifetime data. Add after the history block:

```python
        lifetime_view = self.query_one(LifetimeView)
        if current == "lifetime":
            lt_stats = get_lifetime_stats(self.db)
            # Merge live today data into lifetime totals
            if RUNTIME_JSON.exists():
                try:
                    rt = json.loads(RUNTIME_JSON.read_text())
                    td = rt.get("today", {})
                    if td.get("date") == today:
                        lt_stats["keyboard"] = rt["lifetime"]["keyboard"]
                        lt_stats["mouse"] = rt["lifetime"]["mouse"]
                        lt_stats["total"] = rt["lifetime"]["total"]
                except Exception:
                    pass
            lifetime_view.stats = lt_stats
            lifetime_view.top_keys = get_all_time_top_keys(self.db, limit=20)
```

- [ ] **Step 2: Smoke test LIFETIME tab**

```bash
uv run tapstats
```

Press `4` — LIFETIME tab shows big orange all-time total, all-time top keys bars on the left, stats panel on right (active days, daily avg, record day). Numbers match expectations given DB contents.

- [ ] **Step 3: Run all tests to confirm no regressions**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/tapstats/panel.py
git commit -m "feat(panel): LIFETIME tab with all-time totals, top keys, and record stats"
```
