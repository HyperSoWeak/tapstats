import json
import os
from datetime import date as date_type
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Rule, Static

from .config import get_config
from .db import get_db, get_history, get_top_keys

RUNTIME_JSON = Path(f"/run/user/{os.getuid()}/tapstats.json")
SPARK = " ▁▂▃▄▅▆▇█"


def _bar(value: int, max_val: int, width: int = 24) -> str:
    if max_val == 0:
        return " " * width
    filled = round(value / max_val * width)
    return "█" * filled + " " * (width - filled)


def _spark_char(value: int, max_val: int) -> str:
    if max_val == 0:
        return SPARK[0]
    return SPARK[min(8, round(value / max_val * 8))]


class DashboardHeader(Static):
    data: reactive[dict] = reactive({})

    def render(self) -> str:
        d = self.data
        date = d.get("date", str(date_type.today()))
        kb = d.get("keyboard_total", 0)
        mouse = d.get("mouse", {})
        clicks = mouse.get("left", 0) + mouse.get("right", 0) + mouse.get("middle", 0)
        return f" {date}    ⌨  {kb:,}    🖱  {clicks:,}"


class SummaryPanel(Static):
    today_keys: reactive[int] = reactive(0)
    today_mouse: reactive[dict] = reactive({})

    def render(self) -> str:
        m = self.today_mouse
        return (
            f"[bold]KEYBOARD[/bold]\n"
            f"  Total     [green]{self.today_keys:>8,}[/green]\n\n"
            f"[bold]MOUSE[/bold]\n"
            f"  Left      [green]{m.get('left', 0):>8,}[/green]\n"
            f"  Right     [green]{m.get('right', 0):>8,}[/green]\n"
            f"  Middle    [green]{m.get('middle', 0):>8,}[/green]\n"
            f"  Scroll ↑  [green]{m.get('scroll_up', 0):>8,}[/green]\n"
            f"  Scroll ↓  [green]{m.get('scroll_down', 0):>8,}[/green]"
        )


class TopKeysPanel(Static):
    top_keys: reactive[list] = reactive([])

    def render(self) -> str:
        if not self.top_keys:
            return "[bold]TOP KEYS[/bold]\n\n[dim]No data yet[/dim]"
        max_count = self.top_keys[0][1] if self.top_keys else 1
        lines = ["[bold]TOP KEYS[/bold]\n"]
        for name, count in self.top_keys:
            label = name.replace("KEY_", "")[:12]
            bar = _bar(count, max_count, 22)
            lines.append(f"[cyan]{label:<12}[/cyan] [green]{bar}[/green] {count:,}")
        return "\n".join(lines)


class HistoryPanel(Static):
    history: reactive[list] = reactive([])

    def render(self) -> str:
        cfg = get_config()
        label = f"{cfg.panel.history_days} DAYS"
        if not self.history:
            return f"[bold]{label}[/bold]\n\n[dim]No data yet[/dim]"
        max_val = max((r["total"] for r in self.history), default=0)
        spark = "".join(_spark_char(r["total"], max_val) for r in self.history)
        lines = [f"[bold]{label}[/bold]  [green]{spark}[/green]\n"]
        for r in self.history:
            bar = _bar(r["total"], max_val, 30)
            lines.append(f"[dim]{r['date']}[/dim]  [green]{bar}[/green]  {r['total']:,}")
        return "\n".join(lines)


class TapStatsApp(App):
    TITLE = "tapstats"
    CSS = """
    Screen {
        background: $surface;
    }

    #outer {
        height: 100%;
        border: heavy $accent;
        border-title-align: left;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 0;
    }

    DashboardHeader {
        height: 1;
        background: $accent;
        color: $background;
        text-style: bold;
    }

    #middle {
        height: 1fr;
        border-top: heavy $accent-darken-1;
        border-bottom: heavy $accent-darken-1;
    }

    SummaryPanel {
        width: 26;
        padding: 1 2;
        border-right: heavy $accent-darken-1;
    }

    TopKeysPanel {
        width: 1fr;
        padding: 1 2;
    }

    HistoryPanel {
        padding: 1 2;
        height: auto;
    }

    Rule {
        color: $accent-darken-1;
        margin: 0;
    }

    Footer {
        background: $surface;
        color: $text-muted;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="outer"):
            yield DashboardHeader(id="header")
            with Horizontal(id="middle"):
                yield SummaryPanel()
                yield TopKeysPanel()
            yield HistoryPanel()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#outer").border_title = " TAPSTATS "
        self.db = get_db()
        self.action_refresh()
        self.set_interval(5.0, self.action_refresh)

    def action_refresh(self) -> None:
        cfg = get_config()
        today = str(date_type.today())

        header = self.query_one(DashboardHeader)
        summary = self.query_one(SummaryPanel)
        top = self.query_one(TopKeysPanel)
        hist = self.query_one(HistoryPanel)

        hist.history = get_history(self.db, cfg.panel.history_days)

        if RUNTIME_JSON.exists():
            try:
                data = json.loads(RUNTIME_JSON.read_text())
                if data.get("date") == today:
                    kb_total = data["keyboard"]["total"]
                    mouse = data["mouse"]
                    header.data = {"date": today, "keyboard_total": kb_total, "mouse": mouse}
                    summary.today_keys = kb_total
                    summary.today_mouse = mouse
                    top.top_keys = [(name, count) for name, count in data["keyboard"]["top"]]
                    return
            except Exception:
                pass

        db_top = get_top_keys(self.db, today)
        kb_total = sum(r["count"] for r in db_top)
        header.data = {"date": today, "keyboard_total": kb_total, "mouse": {}}
        summary.today_keys = kb_total
        summary.today_mouse = {}
        top.top_keys = [(r["key_name"], r["count"]) for r in db_top]


def main() -> None:
    TapStatsApp().run()
