import json
import os
from datetime import date as date_type, timedelta
from pathlib import Path

from rich.style import Style
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import ContentSwitcher, Footer, ListItem, ListView, Static

from .config import get_config
from .db import (
    get_all_time_keys,
    get_db,
    get_day_stats,
    get_history,
    get_history_summary,
    get_lifetime_stats,
    get_period_totals,
    get_top_keys,
)
from ._util import fmt_compact as _compact

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


# ── tab bar ──────────────────────────────────────────────────────────────────

class TabBar(Static):
    active: reactive[str] = reactive("overview")

    _TABS = [
        ("overview", "1 OVERVIEW"),
        ("keys",     "2 KEYS"),
        ("history",  "3 HISTORY"),
    ]

    def render(self) -> str:
        parts = []
        for key, label in self._TABS:
            if key == self.active:
                parts.append(f"[reverse bold] {label} [/reverse bold]")
            else:
                parts.append(f"[dim] {label} [/dim]")
        return "  ".join(parts)


# ── overview tab ─────────────────────────────────────────────────────────────

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
            f"[dim]\U000f030c {self.keyboard_total:,}  \U000f037d {self.clicks:,}[/dim]"
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


class OverviewView(Static):
    keyboard_total: reactive[int] = reactive(0)
    top_keys: reactive[list] = reactive([])
    mouse: reactive[dict] = reactive({})
    trend_rows: reactive[list] = reactive([])
    this_period: reactive[int] = reactive(0)
    previous_period: reactive[int] = reactive(0)
    lifetime: reactive[dict] = reactive({})

    def compose(self) -> ComposeResult:
        yield Static(id="overview-today")
        with Horizontal(id="overview-row-a"):
            yield Static(id="overview-top-keys")
            yield Static(id="overview-trend")
        with Horizontal(id="overview-row-b"):
            yield Static(id="overview-mouse")
            yield Static(id="overview-lifetime")

    def on_mount(self) -> None:
        self._render()

    def watch_keyboard_total(self, _: int) -> None:
        if self.is_mounted:
            self._render()

    def watch_top_keys(self, _: list) -> None:
        if self.is_mounted:
            self._render()

    def watch_mouse(self, _: dict) -> None:
        if self.is_mounted:
            self._render()

    def watch_trend_rows(self, _: list) -> None:
        if self.is_mounted:
            self._render()

    def watch_this_period(self, _: int) -> None:
        if self.is_mounted:
            self._render()

    def watch_previous_period(self, _: int) -> None:
        if self.is_mounted:
            self._render()

    def watch_lifetime(self, _: dict) -> None:
        if self.is_mounted:
            self._render()

    def _render(self) -> None:
        clicks = _click_total(self.mouse)
        scroll = _scroll_total(self.mouse)
        total = self.keyboard_total + clicks
        delta = _delta_text(self.this_period, self.previous_period)
        delta_part = f"  [dim]{delta}[/dim]" if delta else ""
        lifetime_total = self.lifetime.get("total", 0)
        lifetime_days = self.lifetime.get("active_days", 0)
        lifetime_avg = lifetime_total // lifetime_days if lifetime_days else 0

        self.query_one("#overview-today", Static).update(
            f"[bold]TODAY[/bold]  [dim]{date_type.today()}[/dim]\n"
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


# ── keys tab ─────────────────────────────────────────────────────────────────

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

    def watch_view_date(self, new: str) -> None:
        if not new:
            return
        self._load_data()

    def watch_key_data(self, v: dict) -> None:
        self.query_one(KeyboardHeatmap).key_data = v
        self.query_one(KeysBars).key_data = v

    def watch_mode(self, v: str) -> None:
        switcher = self.query_one(ContentSwitcher)
        switcher.current = "keys-heatmap" if v == "heatmap" else "keys-bars"
        self._update_header()

    def _load_data(self) -> None:
        if not hasattr(self.app, "db"):
            return
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
        mode_label = {"keyboard": "\U000f030c keys", "mouse": "\U000f037d clicks", "total": "total"}.get(self.mode, "total")
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
            f"[dim]\U000f030c {kb:,}  \U000f037d {mouse:,}  ({days} active days)[/dim]"
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
    #overview-row-a {
        margin-bottom: 1;
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
    Footer {
        background: $surface;
        color: $text-muted;
    }
    """
    BINDINGS = [
        Binding("1", "switch_tab('overview')", "Overview", show=False),
        Binding("2", "switch_tab('keys')",     "Keys",     show=False),
        Binding("3", "switch_tab('history')",  "History",  show=False),
        Binding("tab", "next_tab",             "Next tab", show=False),
        Binding("q", "quit",                   "Quit"),
        Binding("r", "refresh",                "Refresh"),
    ]

    _TAB_ORDER = ["overview", "keys", "history"]

    def compose(self) -> ComposeResult:
        yield TabBar()
        with ContentSwitcher(initial="overview"):
            yield OverviewView(id="overview")
            yield KeysView(id="keys")
            yield HistoryView(id="history")
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
        today = str(date_type.today())
        overview_view = self.query_one(OverviewView)

        # Refresh KEYS if active
        current = self.query_one(ContentSwitcher).current
        if current == "keys":
            self.query_one(KeysView)._load_data()

        cfg = get_config()
        hist_view = self.query_one(HistoryView)
        hist_view.history = get_history(self.db, cfg.panel.history_days, hist_view.mode)
        tw, lw = get_period_totals(self.db, 7, hist_view.mode)
        hist_view.this_week = tw
        hist_view.last_week = lw
        overview_view.trend_rows = get_history(self.db, 7, "total")
        overview_view.this_period, overview_view.previous_period = get_period_totals(self.db, 7, "total")
        overview_lifetime = get_lifetime_stats(self.db)

        if RUNTIME_JSON.exists():
            try:
                data = json.loads(RUNTIME_JSON.read_text())
                td = data.get("today", {})
                if td.get("date") == today:
                    lt = data.get("lifetime", {})
                    overview_lifetime["keyboard"] = lt.get("keyboard", overview_lifetime["keyboard"])
                    overview_lifetime["mouse"] = lt.get("mouse", overview_lifetime["mouse"])
                    overview_lifetime["total"] = lt.get("total", overview_lifetime["total"])
                    overview_view.lifetime = overview_lifetime
                    overview_view.keyboard_total = td["keyboard"]["total"]
                    overview_view.top_keys = [(n, c) for n, c in td["keyboard"]["top"]]
                    overview_view.mouse = td["mouse"]
                    return
            except Exception:
                pass

        overview_view.lifetime = overview_lifetime
        stats = get_day_stats(self.db, today)
        overview_view.keyboard_total = stats["keyboard_total"]
        overview_view.top_keys = stats["top_keys"]
        overview_view.mouse = stats["mouse"]


def main() -> None:
    TapStatsApp().run()
