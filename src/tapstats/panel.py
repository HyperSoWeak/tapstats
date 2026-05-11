import json
import os
from datetime import date as date_type, timedelta
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import ContentSwitcher, Footer, ListItem, ListView, Static

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
