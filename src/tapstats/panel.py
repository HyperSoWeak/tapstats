import json
import os
from datetime import date as date_type, timedelta
from pathlib import Path

from rich.style import Style
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
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
PRIMARY = "#7dcfff"
ACCENT = "#9ece6a"
WARN = "#e0af68"

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
        parts = [f"[bold {PRIMARY}]tapstats[/bold {PRIMARY}]", f"[dim]{date_type.today()}[/dim]", ""]
        for key, label in self._TABS:
            if key == self.active:
                parts.append(f"[reverse bold {PRIMARY}] {label.lower()} [/reverse bold {PRIMARY}]")
            else:
                parts.append(f"[dim] {label.lower()} [/dim]")
        return "  ".join(parts)


# ── overview tab ─────────────────────────────────────────────────────────────

class OverviewView(Container):
    keyboard_total: reactive[int] = reactive(0)
    top_keys: reactive[list] = reactive([])
    mouse: reactive[dict] = reactive({})
    trend_rows: reactive[list] = reactive([])
    this_period: reactive[int] = reactive(0)
    previous_period: reactive[int] = reactive(0)
    lifetime: reactive[dict] = reactive({})

    def render(self) -> str:
        return ""

    def compose(self) -> ComposeResult:
        yield Static(id="overview-today")
        with Horizontal(id="overview-row-a"):
            yield Static(id="overview-top-keys")
            yield Static(id="overview-trend")
        with Horizontal(id="overview-row-b"):
            yield Static(id="overview-mouse")
            yield Static(id="overview-lifetime")

    def on_mount(self) -> None:
        self.query_one("#overview-today", Static).border_title = "today"
        self.query_one("#overview-top-keys", Static).border_title = "keyboard"
        self.query_one("#overview-trend", Static).border_title = "activity"
        self.query_one("#overview-mouse", Static).border_title = "mouse"
        self.query_one("#overview-lifetime", Static).border_title = "lifetime"
        self._update_display()

    def watch_keyboard_total(self, _: int) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_top_keys(self, _: list) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_mouse(self, _: dict) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_trend_rows(self, _: list) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_this_period(self, _: int) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_previous_period(self, _: int) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_lifetime(self, _: dict) -> None:
        if self.is_mounted:
            self._update_display()

    def _update_display(self) -> None:
        clicks = _click_total(self.mouse)
        scroll = _scroll_total(self.mouse)
        total = self.keyboard_total + clicks
        delta = _delta_text(self.this_period, self.previous_period)
        delta_part = f"  [dim]{delta}[/dim]" if delta else ""
        lifetime_total = self.lifetime.get("total", 0)
        lifetime_days = self.lifetime.get("active_days", 0)
        lifetime_avg = lifetime_total // lifetime_days if lifetime_days else 0

        self.query_one("#overview-today", Static).update(
            f"[bold {PRIMARY}]{total:,}[/bold {PRIMARY}] [dim]actions[/dim]\n"
            f"[dim]keys[/dim] {self.keyboard_total:,}   "
            f"[dim]clicks[/dim] {clicks:,}   "
            f"[dim]scroll[/dim] {scroll:,}"
        )

        top_lines = []
        if self.top_keys:
            max_count = self.top_keys[0][1]
            for name, count in self.top_keys[:5]:
                label = name.replace("KEY_", "")[:10]
                bar = _bar(count, max_count, 10)
                top_lines.append(f"[dim]{label:<10}[/dim] [{PRIMARY}]{bar}[/{PRIMARY}] {count:,}")
        else:
            top_lines.append("[dim]No data[/dim]")
        self.query_one("#overview-top-keys", Static).update("\n".join(top_lines))

        self.query_one("#overview-trend", Static).update(
            f"[{ACCENT}]{_trend_text(self.trend_rows)}[/{ACCENT}]\n"
            f"[dim]7d[/dim] {self.this_period:,}{delta_part}"
        )

        self.query_one("#overview-mouse", Static).update(
            f"[dim]left[/dim] {self.mouse.get('left', 0):,}  "
            f"[dim]right[/dim] {self.mouse.get('right', 0):,}\n"
            f"[dim]middle[/dim] {self.mouse.get('middle', 0):,}  "
            f"[dim]scroll[/dim] {scroll:,}"
        )

        self.query_one("#overview-lifetime", Static).update(
            f"[{WARN}]{lifetime_total:,}[/{WARN}] [dim]total[/dim]\n"
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
        for name, count in items:
            label = name.replace("KEY_", "")[:12]
            bar = _bar(count, max_count, 22)
            lines.append(f"[dim]{label:<12}[/dim]  [{PRIMARY}]{bar}[/{PRIMARY}]  {count:,}")
        return "\n".join(lines)


class KeysView(Container):
    BINDINGS = [
        Binding("h", "mode_heatmap", "Heatmap", show=True),
        Binding("b", "mode_bars",    "Bars",    show=True),
        Binding("a", "toggle_scope", "All-time", show=True),
        Binding("left",  "prev_day", "Prev day", show=False),
        Binding("right", "next_day", "Next day", show=False),
    ]

    view_date: reactive[str] = reactive("")
    mode: reactive[str] = reactive("heatmap")
    scope: reactive[str] = reactive("day")
    key_data: reactive[dict] = reactive({})

    def render(self) -> str:
        return ""

    def compose(self) -> ComposeResult:
        yield Static(id="keys-header")
        with ContentSwitcher(initial="keys-heatmap"):
            yield KeyboardHeatmap(id="keys-heatmap")
            yield KeysBars(id="keys-bars")

    def on_mount(self) -> None:
        self.query_one("#keys-header", Static).border_title = "keys"
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

    def watch_scope(self, _: str) -> None:
        self._load_data()

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

    def _update_header(self) -> None:
        mode_label = "heatmap (b: bars)" if self.mode == "heatmap" else "bars (h: heatmap)"
        is_today = self.view_date == str(date_type.today())
        date_label = "today" if is_today else self.view_date
        scope_label = "all-time" if self.scope == "all-time" else date_label
        nav_hint = "a: day" if self.scope == "all-time" else "←/→ days  a: all-time"
        self.query_one("#keys-header", Static).update(
            f"[bold]KEYS[/bold]  [dim]{scope_label}  {nav_hint}  {mode_label}[/dim]"
        )

    def action_mode_heatmap(self) -> None:
        self.mode = "heatmap"

    def action_mode_bars(self) -> None:
        self.mode = "bars"

    def action_prev_day(self) -> None:
        if self.scope == "all-time":
            return
        d = date_type.fromisoformat(self.view_date) - timedelta(days=1)
        self.view_date = str(d)

    def action_next_day(self) -> None:
        if self.scope == "all-time":
            return
        d = date_type.fromisoformat(self.view_date) + timedelta(days=1)
        if d <= date_type.today():
            self.view_date = str(d)

    def action_toggle_scope(self) -> None:
        self.scope = "day" if self.scope == "all-time" else "all-time"


class HistoryItem(ListItem):
    def __init__(self, row: dict, max_val: int) -> None:
        super().__init__()
        self._row = row
        self._max_val = max_val

    def compose(self) -> ComposeResult:
        bar = _bar(self._row["total"], self._max_val, 28)
        text = (
            f"[dim]{self._row['date']}[/dim]  "
            f"[{PRIMARY}]{bar}[/{PRIMARY}]  "
            f"{self._row['total']:,}"
        )
        yield Static(text)


class HistoryView(Container):
    BINDINGS = [
        Binding("enter", "drill_down", "Drill down", show=True),
        Binding("escape", "exit_detail", "Back", show=False),
        Binding("k", "mode_keyboard", "Keyboard", show=False),
        Binding("m", "mode_mouse",    "Mouse",    show=False),
        Binding("t", "mode_total",    "Total",    show=False),
    ]

    history: reactive[list] = reactive([])
    mode: reactive[str] = reactive("total")
    this_week: reactive[int] = reactive(0)
    last_week: reactive[int] = reactive(0)
    trend_7d: reactive[list] = reactive([])
    trend_30d: reactive[list] = reactive([])
    summary: reactive[dict] = reactive({})
    detail_date: reactive[str | None] = reactive(None)
    detail_stats: reactive[dict] = reactive({})

    def render(self) -> str:
        return ""

    def compose(self) -> ComposeResult:
        yield Static(id="history-trend")
        yield Static(id="history-records")
        yield ListView(id="history-list")
        yield Static(id="history-detail")
        yield Static(id="history-footer")

    def on_mount(self) -> None:
        self.query_one("#history-trend", Static).border_title = "trend"
        self.query_one("#history-records", Static).border_title = "records"
        self.query_one("#history-list", ListView).border_title = "daily"
        self.query_one("#history-detail", Static).border_title = "detail"
        self.query_one("#history-detail", Static).display = False
        self._update_analytics()

    def watch_history(self, rows: list) -> None:
        self._rebuild_list(rows)

    def watch_mode(self, _: str) -> None:
        if self.is_mounted:
            self._update_analytics()
        self._update_footer()

    def watch_this_week(self, _: int) -> None:
        if self.is_mounted:
            self._update_analytics()
            self._update_footer()

    def watch_last_week(self, _: int) -> None:
        if self.is_mounted:
            self._update_analytics()
            self._update_footer()

    def watch_trend_7d(self, _: list) -> None:
        if self.is_mounted:
            self._update_analytics()

    def watch_trend_30d(self, _: list) -> None:
        if self.is_mounted:
            self._update_analytics()

    def watch_summary(self, _: dict) -> None:
        if self.is_mounted:
            self._update_analytics()

    def watch_detail_date(self, _: str | None) -> None:
        if self.is_mounted:
            self._update_detail()

    def watch_detail_stats(self, _: dict) -> None:
        if self.is_mounted:
            self._update_detail()

    def _rebuild_list(self, rows: list) -> None:
        lv = self.query_one(ListView)
        lv.clear()
        displayed = list(reversed(rows))
        max_val = max((r["total"] for r in displayed), default=1)
        for row in displayed:
            lv.append(HistoryItem(row, max_val))

    def _update_analytics(self) -> None:
        delta = _delta_text(self.this_week, self.last_week)
        delta_part = f"  [dim]{delta}[/dim]" if delta else ""
        self.query_one("#history-trend", Static).update(
            f"[dim]{self.mode}[/dim]\n"
            f"7d  [{ACCENT}]{_trend_text(self.trend_7d)}[/{ACCENT}]  {self.this_week:,}{delta_part}\n"
            f"30d [{PRIMARY}]{_trend_text(self.trend_30d)}[/{PRIMARY}]  "
            f"[dim]avg/day[/dim] {self.summary.get('daily_avg', 0):,}"
        )
        self.query_one("#history-records", Static).update(
            f"[dim]best day[/dim]   {self.summary.get('best_total', 0):,}  "
            f"[dim]{self.summary.get('best_date', '')}[/dim]\n"
            f"[dim]low day [/dim]   {self.summary.get('low_total', 0):,}  "
            f"[dim]{self.summary.get('low_date', '')}[/dim]\n"
            f"[dim]active[/dim]     {self.summary.get('active_days', 0)}/{self.summary.get('window_days', 0)}"
        )

    def _update_footer(self) -> None:
        mode_label = {"keyboard": "\U000f030c keys", "mouse": "\U000f037d clicks", "total": "total"}.get(self.mode, "total")
        self.query_one("#history-footer", Static).update(
            f"[dim]Enter detail  Esc back  k/m/t filter  ({mode_label})[/dim]"
        )

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
            f"[{PRIMARY}]{total:,} total[/{PRIMARY}]  [dim]keys {keyboard_total:,}  clicks {clicks:,}  scroll {scroll:,}[/dim]",
            "",
            "[dim]top keys[/dim]",
        ]
        top_keys = self.detail_stats.get("top_keys", [])
        max_count = top_keys[0][1] if top_keys else 0
        for name, count in top_keys[:5]:
            label = name.replace("KEY_", "")[:10]
            lines.append(f"[dim]{label:<10}[/dim] [{PRIMARY}]{_bar(count, max_count, 12)}[/{PRIMARY}] {count:,}")
        lines.extend([
            "",
            "[dim]mouse[/dim]",
            f"[dim]left[/dim] {mouse.get('left', 0):,}  [dim]right[/dim] {mouse.get('right', 0):,}  [dim]middle[/dim] {mouse.get('middle', 0):,}",
        ])
        detail.update("\n".join(lines))

    def action_drill_down(self) -> None:
        lv = self.query_one(ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, HistoryItem):
            self.detail_date = lv.highlighted_child._row["date"]
            self.detail_stats = get_day_stats(self.app.db, self.detail_date)  # type: ignore[attr-defined]

    def action_exit_detail(self) -> None:
        self.detail_date = None
        self.detail_stats = {}

    def action_mode_keyboard(self) -> None:
        self.mode = "keyboard"
        self.app.action_refresh()  # type: ignore[attr-defined]

    def action_mode_mouse(self) -> None:
        self.mode = "mouse"
        self.app.action_refresh()  # type: ignore[attr-defined]

    def action_mode_total(self) -> None:
        self.mode = "total"
        self.app.action_refresh()  # type: ignore[attr-defined]


# ── app ───────────────────────────────────────────────────────────────────────

class TapStatsApp(App):
    TITLE = "tapstats"
    CSS = """
    Screen {
        background: #070b10;
    }
    TabBar {
        height: 1;
        background: #070b10;
        padding: 0 1;
        dock: top;
    }
    ContentSwitcher {
        height: 1fr;
    }
    OverviewView {
        height: 100%;
        padding: 1;
    }
    #overview-today {
        height: 5;
        border: round #25566a;
        padding: 0 1;
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
        border: round #25566a;
        padding: 0 1;
        margin-right: 1;
    }
    #overview-trend, #overview-lifetime {
        width: 34;
        border: round #25566a;
        padding: 0 1;
    }
    HistoryView {
        height: 100%;
        padding: 1;
    }
    #history-trend {
        height: 5;
        border: round #25566a;
        padding: 0 1;
        margin-bottom: 1;
    }
    #history-records {
        height: 5;
        border: round #25566a;
        padding: 0 1;
        margin-bottom: 1;
    }
    #history-list {
        height: 1fr;
        border: round #25566a;
        padding: 0 1;
    }
    #history-detail {
        height: 10;
        border: round #25566a;
        margin-top: 1;
        padding: 0 1;
    }
    #history-footer {
        height: 1;
        margin-top: 1;
    }
    HistoryItem {
        padding: 0 0;
        height: 1;
    }
    HistoryItem.--highlight {
        background: #14313d;
    }
    KeysView {
        height: 100%;
        padding: 1;
    }
    #keys-header {
        height: 3;
        border: round #25566a;
        padding: 0 1;
        margin-bottom: 1;
    }
    KeyboardHeatmap {
        height: auto;
        border: round #25566a;
        padding: 1;
    }
    KeysBars {
        height: 1fr;
        border: round #25566a;
        padding: 0 1;
        overflow-y: auto;
    }
    Footer {
        background: #070b10;
        color: #565f70;
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
        hist_view.trend_7d = get_history(self.db, 7, hist_view.mode)
        hist_view.trend_30d = get_history(self.db, 30, hist_view.mode)
        hist_view.this_week, hist_view.last_week = get_period_totals(self.db, 7, hist_view.mode)
        hist_view.summary = get_history_summary(self.db, 30, hist_view.mode)
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
