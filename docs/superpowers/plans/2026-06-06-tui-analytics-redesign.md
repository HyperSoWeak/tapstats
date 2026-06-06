# TUI Analytics Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `tapstats` TUI around `OVERVIEW / KEYS / HISTORY`, add analytics helpers, and change Waybar total mode to use one dedicated total icon.

**Architecture:** Keep the existing Textual app and SQLite schema. Add read-only DB helpers for all-time keys and history summaries, then refactor `panel.py` around three focused views while preserving runtime JSON fallback behavior. Keep Waybar scope to a small icon formatting change.

**Tech Stack:** Python 3.11, Textual, Rich markup, SQLite, pytest, pnpm not used.

---

## File Structure

- Modify `src/tapstats/db.py`: add read-only analytics helpers.
- Modify `src/tapstats/waybar.py`: add `TOTAL_ICON` and use it for `display = "total"`.
- Modify `src/tapstats/panel.py`: replace 4-tab IA with 3-tab analytics UI.
- Modify `tests/test_db.py`: cover new DB helpers.
- Modify `tests/test_waybar.py`: cover dedicated total icon behavior.
- Modify `tests/test_panel_helpers.py`: cover pure panel formatting helpers.
- Modify `README.md`: document the 3-tab TUI and total icon behavior.

Do not modify `PKGBUILD`; it has pre-existing local changes.

## Task 1: Add DB Analytics Helpers

**Files:**
- Modify: `src/tapstats/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing DB tests**

Add these imports in `tests/test_db.py`:

```python
from tapstats.db import (
    _init,
    flush,
    get_all_time_keys,
    get_all_time_top_keys,
    get_day_stats,
    get_history,
    get_history_summary,
    get_lifetime_stats,
    get_lifetime_totals,
    get_period_totals,
    get_top_keys,
    get_week_totals,
)
```

Append these tests:

```python
def test_get_all_time_keys(conn):
    _seed(conn, "2026-05-10", {"KEY_A": 100, "KEY_B": 30}, {})
    _seed(conn, "2026-05-11", {"KEY_A": 50, "KEY_C": 20}, {})

    rows = get_all_time_keys(conn)

    assert rows == [
        {"key_name": "KEY_A", "count": 150},
        {"key_name": "KEY_B", "count": 30},
        {"key_name": "KEY_C", "count": 20},
    ]


def test_get_period_totals_total_mode(conn):
    today = date.today()
    _seed(conn, str(today), {"KEY_A": 100}, {"left": 10, "scroll_up": 999})
    _seed(conn, str(today - timedelta(days=3)), {"KEY_B": 50}, {"right": 5})
    _seed(conn, str(today - timedelta(days=9)), {"KEY_C": 20}, {"left": 2})

    this_period, previous_period = get_period_totals(conn, days=7, mode="total")

    assert this_period == 165
    assert previous_period == 22


def test_get_period_totals_keyboard_mode(conn):
    today = date.today()
    _seed(conn, str(today), {"KEY_A": 100}, {"left": 10})
    _seed(conn, str(today - timedelta(days=8)), {"KEY_B": 50}, {"left": 5})

    this_period, previous_period = get_period_totals(conn, days=7, mode="keyboard")

    assert this_period == 100
    assert previous_period == 50


def test_get_period_totals_mouse_mode_excludes_scroll(conn):
    today = date.today()
    _seed(conn, str(today), {"KEY_A": 100}, {"left": 10, "scroll_down": 900})
    _seed(conn, str(today - timedelta(days=8)), {"KEY_B": 50}, {"right": 5, "scroll_up": 700})

    this_period, previous_period = get_period_totals(conn, days=7, mode="mouse")

    assert this_period == 10
    assert previous_period == 5


def test_get_history_summary(conn):
    today = date.today()
    _seed(conn, str(today), {"KEY_A": 100}, {"left": 10})
    _seed(conn, str(today - timedelta(days=1)), {"KEY_B": 50}, {"right": 5})
    _seed(conn, str(today - timedelta(days=2)), {"KEY_C": 20}, {})

    summary = get_history_summary(conn, days=7, mode="total")

    assert summary == {
        "total": 185,
        "daily_avg": 26,
        "active_days": 3,
        "window_days": 7,
        "best_date": str(today),
        "best_total": 110,
        "low_date": str(today - timedelta(days=2)),
        "low_total": 20,
    }
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_db.py -v
```

Expected: FAIL with import errors for `get_all_time_keys`, `get_period_totals`, and `get_history_summary`.

- [ ] **Step 3: Implement DB helpers**

Add these functions to `src/tapstats/db.py` after `get_all_time_top_keys`:

```python
def get_all_time_keys(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT key_name, SUM(count) AS count FROM daily_keys
        GROUP BY key_name ORDER BY count DESC, key_name ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _daily_totals_sql(mode: str) -> str:
    if mode == "keyboard":
        return """
            SELECT date, SUM(count) AS total FROM daily_keys
            GROUP BY date
        """
    if mode == "mouse":
        return """
            SELECT date, SUM(count) AS total FROM daily_mouse
            WHERE button NOT IN ('scroll_up', 'scroll_down')
            GROUP BY date
        """
    return """
        WITH combined AS (
            SELECT date, count FROM daily_keys
            UNION ALL
            SELECT date, count FROM daily_mouse
            WHERE button NOT IN ('scroll_up', 'scroll_down')
        )
        SELECT date, SUM(count) AS total FROM combined GROUP BY date
    """


def get_period_totals(conn: sqlite3.Connection, days: int, mode: str = "total") -> tuple[int, int]:
    sql = f"""
        WITH daily AS ({_daily_totals_sql(mode)})
        SELECT
            COALESCE(SUM(CASE WHEN date >= date('now', 'localtime', ?) THEN total ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN date >= date('now', 'localtime', ?) AND date < date('now', 'localtime', ?) THEN total ELSE 0 END), 0)
        FROM daily
    """
    current_start = f"-{days - 1} days"
    previous_start = f"-{days * 2 - 1} days"
    row = conn.execute(sql, (current_start, previous_start, current_start)).fetchone()
    return (row[0], row[1])


def get_history_summary(conn: sqlite3.Connection, days: int, mode: str = "total") -> dict:
    sql = f"""
        WITH daily AS ({_daily_totals_sql(mode)}),
        windowed AS (
            SELECT date, total FROM daily
            WHERE date >= date('now', 'localtime', ?)
        )
        SELECT
            COALESCE(SUM(total), 0) AS total,
            COUNT(*) AS active_days,
            (SELECT date FROM windowed ORDER BY total DESC, date DESC LIMIT 1) AS best_date,
            (SELECT total FROM windowed ORDER BY total DESC, date DESC LIMIT 1) AS best_total,
            (SELECT date FROM windowed ORDER BY total ASC, date DESC LIMIT 1) AS low_date,
            (SELECT total FROM windowed ORDER BY total ASC, date DESC LIMIT 1) AS low_total
        FROM windowed
    """
    row = conn.execute(sql, (f"-{days - 1} days",)).fetchone()
    total = row["total"] or 0
    return {
        "total": total,
        "daily_avg": total // days if days else 0,
        "active_days": row["active_days"] or 0,
        "window_days": days,
        "best_date": row["best_date"] or "",
        "best_total": row["best_total"] or 0,
        "low_date": row["low_date"] or "",
        "low_total": row["low_total"] or 0,
    }
```

- [ ] **Step 4: Run DB tests**

Run:

```bash
uv run pytest tests/test_db.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tapstats/db.py tests/test_db.py
git commit -m "feat: add TUI analytics query helpers"
```

## Task 2: Change Waybar Total Icon

**Files:**
- Modify: `src/tapstats/waybar.py`
- Modify: `tests/test_waybar.py`

- [ ] **Step 1: Write failing Waybar test**

Add `TOTAL_ICON` to the import:

```python
from tapstats.waybar import TOTAL_ICON, _format_output, _fmt
```

Replace `test_total_mode_text` with:

```python
def test_total_mode_text_uses_dedicated_icon():
    result = json.loads(_format_output(_data(kb=1000, clicks=200), _cfg(display="total")))
    assert result["text"] == f"{TOTAL_ICON} 1.2k"
    assert "󰌌 󰍽" not in result["text"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_waybar.py::test_total_mode_text_uses_dedicated_icon -v
```

Expected: FAIL because `TOTAL_ICON` is not defined or total mode still uses both icons.

- [ ] **Step 3: Implement total icon**

In `src/tapstats/waybar.py`, add:

```python
TOTAL_ICON = "Σ"
```

Change total display formatting to:

```python
        case "total":
            text = f"{TOTAL_ICON} {fmt(kb + clicks)}"
```

- [ ] **Step 4: Run Waybar tests**

Run:

```bash
uv run pytest tests/test_waybar.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tapstats/waybar.py tests/test_waybar.py
git commit -m "fix(waybar): use dedicated total icon"
```

## Task 3: Add Panel Formatting Helpers

**Files:**
- Modify: `src/tapstats/panel.py`
- Modify: `tests/test_panel_helpers.py`

- [ ] **Step 1: Write failing helper tests**

Append to `tests/test_panel_helpers.py`:

```python
from tapstats.panel import _click_total, _delta_text, _scroll_total, _trend_text


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
```

- [ ] **Step 2: Run helper tests to verify failure**

Run:

```bash
uv run pytest tests/test_panel_helpers.py -v
```

Expected: FAIL because the new helpers are not defined.

- [ ] **Step 3: Implement helpers**

Add these helpers near the existing `_bar` and `_spark_char` helpers in `src/tapstats/panel.py`:

```python
def _click_total(mouse: dict) -> int:
    return mouse.get("left", 0) + mouse.get("right", 0) + mouse.get("middle", 0)


def _scroll_total(mouse: dict) -> int:
    return mouse.get("scroll_up", 0) + mouse.get("scroll_down", 0)


def _delta_text(current: int, previous: int) -> str:
    if previous == 0:
        return ""
    delta = (current - previous) / previous * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}%"


def _trend_text(rows: list[dict]) -> str:
    max_val = max((r["total"] for r in rows), default=0)
    return "".join(_spark_char(r["total"], max_val) for r in rows)
```

- [ ] **Step 4: Run helper tests**

Run:

```bash
uv run pytest tests/test_panel_helpers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tapstats/panel.py tests/test_panel_helpers.py
git commit -m "feat(panel): add analytics formatting helpers"
```

## Task 4: Convert App Shell to Three Tabs

**Files:**
- Modify: `src/tapstats/panel.py`

- [ ] **Step 1: Update tab bar**

Change `TabBar._TABS` to:

```python
    _TABS = [
        ("overview", "1 OVERVIEW"),
        ("keys",     "2 KEYS"),
        ("history",  "3 HISTORY"),
    ]
```

Change `active` default:

```python
    active: reactive[str] = reactive("overview")
```

- [ ] **Step 2: Rename TodayView shell to OverviewView**

Rename `TodayView` to `OverviewView`. Keep the existing today widgets temporarily so the app still runs while later tasks reshape the layout.

Update app composition:

```python
        with ContentSwitcher(initial="overview"):
            yield OverviewView(id="overview")
            yield KeysView(id="keys")
            yield HistoryView(id="history")
```

Remove `LifetimeView` from composition.

- [ ] **Step 3: Update app bindings**

Set bindings to:

```python
    BINDINGS = [
        Binding("1", "switch_tab('overview')", "Overview", show=False),
        Binding("2", "switch_tab('keys')",     "Keys",     show=False),
        Binding("3", "switch_tab('history')",  "History",  show=False),
        Binding("tab", "next_tab",             "Next tab", show=False),
        Binding("q", "quit",                   "Quit"),
        Binding("r", "refresh",                "Refresh"),
    ]

    _TAB_ORDER = ["overview", "keys", "history"]
```

- [ ] **Step 4: Update refresh references**

Replace `today_view = self.query_one(TodayView)` with:

```python
        overview_view = self.query_one(OverviewView)
```

Replace assignments to `today_view` with assignments to `overview_view`. Remove the `current == "lifetime"` block from `action_refresh`; lifetime data will be loaded into overview in Task 5.

- [ ] **Step 5: Run panel import smoke test**

Run:

```bash
uv run python -c "from tapstats.panel import TapStatsApp; app = TapStatsApp(); print(app.TITLE)"
```

Expected output:

```text
tapstats
```

- [ ] **Step 6: Commit**

```bash
git add src/tapstats/panel.py
git commit -m "feat(panel): switch TUI shell to three tabs"
```

## Task 5: Build Overview Dashboard

**Files:**
- Modify: `src/tapstats/panel.py`

- [ ] **Step 1: Add overview state**

Define `OverviewView` with this state:

```python
class OverviewView(Static):
    keyboard_total: reactive[int] = reactive(0)
    top_keys: reactive[list] = reactive([])
    mouse: reactive[dict] = reactive({})
    trend_rows: reactive[list] = reactive([])
    this_period: reactive[int] = reactive(0)
    previous_period: reactive[int] = reactive(0)
    lifetime: reactive[dict] = reactive({})
```

- [ ] **Step 2: Add overview layout**

Use these child ids in `compose()`:

```python
    def compose(self) -> ComposeResult:
        yield Static(id="overview-today")
        with Horizontal(id="overview-row-a"):
            yield Static(id="overview-top-keys")
            yield Static(id="overview-trend")
        with Horizontal(id="overview-row-b"):
            yield Static(id="overview-mouse")
            yield Static(id="overview-lifetime")
```

- [ ] **Step 3: Add overview rendering method**

Implement:

```python
    def _render(self) -> None:
        clicks = _click_total(self.mouse)
        scroll = _scroll_total(self.mouse)
        total = self.keyboard_total + clicks
        delta = _delta_text(self.this_period, self.previous_period)
        delta_part = f"  {delta}" if delta else ""
        lifetime_total = self.lifetime.get("total", 0)
        lifetime_days = self.lifetime.get("active_days", 0)
        lifetime_avg = lifetime_total // lifetime_days if lifetime_days else 0

        self.query_one("#overview-today", Static).update(
            f"[bold]TODAY[/bold]\n"
            f"[bold green]{total:,} actions[/bold green]\n"
            f"[dim]keys {self.keyboard_total:,}  clicks {clicks:,}  scroll ±{scroll:,}[/dim]"
        )

        top_lines = ["[bold]TOP KEYS TODAY[/bold]"]
        if self.top_keys:
            max_count = self.top_keys[0][1]
            for i, (name, count) in enumerate(self.top_keys[:5]):
                color = BAR_COLORS[i % len(BAR_COLORS)]
                label = name.replace("KEY_", "")[:10]
                top_lines.append(f"[dim]{label:<10}[/dim] [{color}]{_bar(count, max_count, 12)}[/{color}] {count:,}")
        else:
            top_lines.append("[dim]No data[/dim]")
        self.query_one("#overview-top-keys", Static).update("\n".join(top_lines))

        self.query_one("#overview-trend", Static).update(
            f"[bold]7-DAY TREND[/bold]\n"
            f"[green]{_trend_text(self.trend_rows)}[/green]\n"
            f"[dim]this 7d[/dim] {self.this_period:,}{delta_part}"
        )

        self.query_one("#overview-mouse", Static).update(
            f"[bold]MOUSE TODAY[/bold]\n"
            f"[dim]left[/dim] {self.mouse.get('left', 0):,}  "
            f"[dim]right[/dim] {self.mouse.get('right', 0):,}\n"
            f"[dim]middle[/dim] {self.mouse.get('middle', 0):,}  "
            f"[dim]scroll[/dim] ±{scroll:,}"
        )

        self.query_one("#overview-lifetime", Static).update(
            f"[bold]LIFETIME[/bold]\n"
            f"[#ff9e64]{lifetime_total:,} actions[/#ff9e64]\n"
            f"[dim]avg/day[/dim] {lifetime_avg:,}\n"
            f"[dim]record[/dim] {self.lifetime.get('record_total', 0):,}  "
            f"[dim]{self.lifetime.get('record_date', '')}[/dim]"
        )
```

- [ ] **Step 4: Wire watchers**

For every overview reactive field, call `_render()` after mount:

```python
    def watch_keyboard_total(self, _: int) -> None:
        if self.is_mounted:
            self._render()
```

Repeat the same pattern for `top_keys`, `mouse`, `trend_rows`, `this_period`, `previous_period`, and `lifetime`.

- [ ] **Step 5: Update refresh data flow**

In `TapStatsApp.action_refresh()`, load overview analytics:

```python
        overview_view.trend_rows = get_history(self.db, 7, "total")
        overview_view.this_period, overview_view.previous_period = get_period_totals(self.db, 7, "total")
        overview_view.lifetime = get_lifetime_stats(self.db)
```

When current runtime JSON exists for today, merge runtime lifetime values into `overview_view.lifetime`.

- [ ] **Step 6: Update CSS**

Replace `TodayView` CSS with:

```css
    OverviewView {
        height: 100%;
        padding: 1 2;
    }
    #overview-today {
        height: 5;
        border-bottom: solid $accent-darken-1;
        margin-bottom: 1;
    }
    #overview-row-a, #overview-row-b {
        height: 1fr;
    }
    #overview-top-keys, #overview-mouse {
        width: 1fr;
        padding-right: 2;
        border-right: solid $accent-darken-1;
    }
    #overview-trend, #overview-lifetime {
        width: 34;
        padding-left: 2;
    }
```

- [ ] **Step 7: Run smoke test**

Run:

```bash
uv run python -c "from tapstats.panel import OverviewView, TapStatsApp; print(OverviewView.__name__, TapStatsApp.TITLE)"
```

Expected output:

```text
OverviewView tapstats
```

- [ ] **Step 8: Commit**

```bash
git add src/tapstats/panel.py
git commit -m "feat(panel): add overview analytics dashboard"
```

## Task 6: Add KEYS All-Time Scope

**Files:**
- Modify: `src/tapstats/panel.py`

- [ ] **Step 1: Update imports**

Add `get_all_time_keys` to the DB imports:

```python
from .db import (
    get_all_time_keys,
    get_all_time_top_keys,
    get_db,
    get_day_stats,
    get_history,
    get_history_summary,
    get_lifetime_stats,
    get_period_totals,
    get_top_keys,
)
```

- [ ] **Step 2: Add scope binding and state**

In `KeysView.BINDINGS`, add:

```python
        Binding("a", "toggle_scope", "All-time", show=True),
```

Add:

```python
    scope: reactive[str] = reactive("day")
```

- [ ] **Step 3: Update key loading**

Replace `_load_data()` body with:

```python
    def _load_data(self) -> None:
        if not hasattr(self.app, "db"):
            return
        if self.scope == "all-time":
            rows = get_all_time_keys(self.app.db)  # type: ignore[attr-defined]
            self.key_data = {r["key_name"]: r["count"] for r in rows}
        else:
            rows = get_top_keys(self.app.db, self.view_date, limit=None)  # type: ignore[attr-defined]
            self.key_data = {r["key_name"]: r["count"] for r in rows}
        self._update_header()
```

- [ ] **Step 4: Update header and navigation**

In `_update_header()`, include scope:

```python
        scope_label = "all-time" if self.scope == "all-time" else date_label
        nav_hint = "a: day" if self.scope == "all-time" else "←/→ days  a: all-time"
        self.query_one("#keys-header", Static).update(
            f"[bold]KEYS[/bold]  [dim]{scope_label}  {nav_hint}  {mode_label}[/dim]"
        )
```

In `action_prev_day()` and `action_next_day()`, return early when all-time:

```python
        if self.scope == "all-time":
            return
```

- [ ] **Step 5: Add toggle action**

```python
    def action_toggle_scope(self) -> None:
        self.scope = "day" if self.scope == "all-time" else "all-time"
        self._load_data()
```

- [ ] **Step 6: Run smoke test**

Run:

```bash
uv run python -c "from tapstats.panel import KeysView; print(KeysView.__name__)"
```

Expected output:

```text
KeysView
```

- [ ] **Step 7: Commit**

```bash
git add src/tapstats/panel.py
git commit -m "feat(panel): add all-time keys scope"
```

## Task 7: Rebuild HISTORY as Trend Analytics

**Files:**
- Modify: `src/tapstats/panel.py`

- [ ] **Step 1: Update imports**

Ensure `get_history_summary` and `get_period_totals` are imported from `.db`.

- [ ] **Step 2: Add history state**

Add to `HistoryView`:

```python
    trend_7d: reactive[list] = reactive([])
    trend_30d: reactive[list] = reactive([])
    summary: reactive[dict] = reactive({})
    detail_date: reactive[str | None] = reactive(None)
    detail_stats: reactive[dict] = reactive({})
```

- [ ] **Step 3: Update history layout**

Replace `compose()` with:

```python
    def compose(self) -> ComposeResult:
        yield Static(id="history-trend")
        yield Static(id="history-records")
        yield ListView(id="history-list")
        yield Static(id="history-detail")
        yield Static(id="history-footer")
```

- [ ] **Step 4: Render trend and records**

Add:

```python
    def _update_analytics(self) -> None:
        delta = _delta_text(self.this_week, self.last_week)
        delta_part = f"  {delta}" if delta else ""
        self.query_one("#history-trend", Static).update(
            f"[bold]TREND[/bold]  [dim]{self.mode}[/dim]\n"
            f"7d  [green]{_trend_text(self.trend_7d)}[/green]  {self.this_week:,}{delta_part}\n"
            f"30d [blue]{_trend_text(self.trend_30d)}[/blue]  "
            f"[dim]avg/day[/dim] {self.summary.get('daily_avg', 0):,}"
        )
        self.query_one("#history-records", Static).update(
            f"[bold]RECORDS[/bold]\n"
            f"[dim]best day[/dim]   {self.summary.get('best_total', 0):,}  "
            f"[dim]{self.summary.get('best_date', '')}[/dim]\n"
            f"[dim]low day [/dim]   {self.summary.get('low_total', 0):,}  "
            f"[dim]{self.summary.get('low_date', '')}[/dim]\n"
            f"[dim]active[/dim]     {self.summary.get('active_days', 0)}/{self.summary.get('window_days', 0)}"
        )
```

- [ ] **Step 5: Add detail rendering**

Add:

```python
    def _update_detail(self) -> None:
        detail = self.query_one("#history-detail", Static)
        if self.detail_date is None:
            detail.display = False
            return
        detail.display = True
        mouse = self.detail_stats.get("mouse", {})
        clicks = _click_total(mouse)
        scroll = _scroll_total(mouse)
        keyboard_total = self.detail_stats.get("keyboard_total", 0)
        total = keyboard_total + clicks
        lines = [
            f"[bold]DETAIL {self.detail_date}[/bold]",
            f"[green]{total:,} total[/green]  [dim]keys {keyboard_total:,}  clicks {clicks:,}  scroll ±{scroll:,}[/dim]",
            "",
            "[bold]TOP KEYS[/bold]",
        ]
        top_keys = self.detail_stats.get("top_keys", [])
        max_count = top_keys[0][1] if top_keys else 0
        for i, (name, count) in enumerate(top_keys[:5]):
            color = BAR_COLORS[i % len(BAR_COLORS)]
            label = name.replace("KEY_", "")[:10]
            lines.append(f"[dim]{label:<10}[/dim] [{color}]{_bar(count, max_count, 12)}[/{color}] {count:,}")
        lines.extend([
            "",
            "[bold]MOUSE[/bold]",
            f"[dim]left[/dim] {mouse.get('left', 0):,}  [dim]right[/dim] {mouse.get('right', 0):,}  [dim]middle[/dim] {mouse.get('middle', 0):,}",
        ])
        detail.update("\n".join(lines))
```

- [ ] **Step 6: Wire watchers**

Call `_update_analytics()` from watchers for `trend_7d`, `trend_30d`, `summary`, `this_week`, `last_week`, and `mode` when mounted. Call `_update_detail()` from watchers for `detail_date` and `detail_stats`.

- [ ] **Step 7: Change drill-down behavior**

Replace `action_drill_down()` with:

```python
    def action_drill_down(self) -> None:
        lv = self.query_one(ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, HistoryItem):
            self.detail_date = lv.highlighted_child._row["date"]
            self.detail_stats = get_day_stats(self.app.db, self.detail_date)  # type: ignore[attr-defined]
```

Add:

```python
    def action_exit_detail(self) -> None:
        self.detail_date = None
        self.detail_stats = {}
```

Use `Escape` binding locally:

```python
        Binding("escape", "exit_detail", "Back", show=False),
```

- [ ] **Step 8: Update app refresh**

In `TapStatsApp.action_refresh()`, after loading `hist_view.history`, set:

```python
        hist_view.trend_7d = get_history(self.db, 7, hist_view.mode)
        hist_view.trend_30d = get_history(self.db, 30, hist_view.mode)
        hist_view.this_week, hist_view.last_week = get_period_totals(self.db, 7, hist_view.mode)
        hist_view.summary = get_history_summary(self.db, 30, hist_view.mode)
```

- [ ] **Step 9: Remove app-level drill-down switching**

Delete `on_drill_down()` and `on_drill_down_exit()` from `TapStatsApp`; history detail is now local to `HistoryView`.

- [ ] **Step 10: Run smoke test**

Run:

```bash
uv run python -c "from tapstats.panel import HistoryView; print(HistoryView.__name__)"
```

Expected output:

```text
HistoryView
```

- [ ] **Step 11: Commit**

```bash
git add src/tapstats/panel.py
git commit -m "feat(panel): rebuild history analytics view"
```

## Task 8: Remove LifetimeView and Clean Panel CSS

**Files:**
- Modify: `src/tapstats/panel.py`

- [ ] **Step 1: Delete lifetime-specific code**

Remove the `LifetimeView` class and all CSS blocks for:

```text
LifetimeView
#lifetime-header
#lifetime-cols
#lifetime-bars
#lifetime-stats
```

- [ ] **Step 2: Remove obsolete messages**

Remove `DrillDown` and `DrillDownExit` if no longer referenced after Task 7.

- [ ] **Step 3: Check references**

Run:

```bash
rg -n "LifetimeView|DrillDown|DrillDownExit|today_view|TodayView|lifetime" src/tapstats/panel.py
```

Expected: only legitimate overview lifetime references remain; no `LifetimeView`, `TodayView`, `DrillDown`, or `DrillDownExit`.

- [ ] **Step 4: Run panel helper tests**

Run:

```bash
uv run pytest tests/test_panel_helpers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tapstats/panel.py
git commit -m "refactor(panel): remove obsolete lifetime tab code"
```

## Task 9: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update project summary**

Change:

```markdown
Track daily keyboard and mouse activity. Shows live stats in Waybar and a 4-tab TUI dashboard.
```

To:

```markdown
Track daily keyboard and mouse activity. Shows live stats in Waybar and a 3-tab analytics TUI.
```

- [ ] **Step 2: Replace TUI table**

Replace the TUI tab table with:

```markdown
Three tabs, navigate with `1`–`3` or `Tab`:

| Tab | Content |
|-----|---------|
| **OVERVIEW** | Today total, keyboard/click/scroll summary, top keys, 7-day trend, lifetime summary |
| **KEYS** | QWERTY heatmap or ranked bars; `←`/`→` navigate days; `a` toggles day/all-time; `b` bars; `h` heatmap |
| **HISTORY** | 7-day and 30-day trends, records, daily list, in-tab day detail; `k`/`m`/`t` filter keyboard / mouse / total |
```

- [ ] **Step 3: Update key list**

Change:

```markdown
Other keys: `r` refresh, `q` quit.
```

To:

```markdown
Other keys: `Enter` drill into a selected history day, `Esc` return from detail, `r` refresh, `q` quit.
```

- [ ] **Step 4: Update Waybar description**

Add after the Waybar paragraph:

```markdown
When `display = "total"`, the module uses a single total icon instead of combining the keyboard and mouse icons.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: update TUI analytics README"
```

## Task 10: Final Verification

**Files:**
- No code changes unless verification exposes a bug.

- [ ] **Step 1: Run full tests**

Run:

```bash
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 2: Run import smoke tests**

Run:

```bash
uv run python -c "from tapstats.panel import TapStatsApp; from tapstats.waybar import TOTAL_ICON; print(TapStatsApp.TITLE, TOTAL_ICON)"
```

Expected output:

```text
tapstats Σ
```

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: no uncommitted files from this implementation. Pre-existing `PKGBUILD` may still appear and must remain unstaged unless the user separately asks to handle it.

- [ ] **Step 4: Fix verification failures**

If a test fails, make the smallest code change that directly addresses the failing assertion, rerun the failing test, then rerun `uv run pytest -v`.

- [ ] **Step 5: Commit verification fix if needed**

Only if Step 4 changed files:

```bash
git add src/tapstats tests README.md
git commit -m "fix: complete TUI analytics verification"
```

## Self-Review

- Spec coverage: Tasks cover DB helpers, Waybar total icon, `OVERVIEW`, `KEYS`, `HISTORY`, lifetime tab removal, README, and final verification.
- Placeholder scan: no placeholder markers or omitted code blocks are used.
- Type consistency: helper names match the spec and are imported where later tasks need them.
