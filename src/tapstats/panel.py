import json
import os
from datetime import date as date_type
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

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


class SummaryPanel(Static):
    today_keys: reactive[int] = reactive(0)
    today_mouse: reactive[dict] = reactive({})

    def render(self) -> str:
        m = self.today_mouse
        return (
            f"[bold]Today[/bold]  {date_type.today()}\n\n"
            f"[dim]⌨[/dim]  Keyboard    [green]{self.today_keys:>8,}[/green]\n\n"
            f"[dim]🖱[/dim]  Left        [green]{m.get('left', 0):>8,}[/green]\n"
            f"   Right       [green]{m.get('right', 0):>8,}[/green]\n"
            f"   Middle      [green]{m.get('middle', 0):>8,}[/green]\n"
            f"   Scroll ↑    [green]{m.get('scroll_up', 0):>8,}[/green]\n"
            f"   Scroll ↓    [green]{m.get('scroll_down', 0):>8,}[/green]"
        )


class TopKeysPanel(Static):
    top_keys: reactive[list] = reactive([])

    def render(self) -> str:
        if not self.top_keys:
            return "[bold]Top Keys[/bold]\n\n[dim]No data yet[/dim]"
        max_count = self.top_keys[0][1] if self.top_keys else 1
        lines = ["[bold]Top Keys[/bold]\n"]
        for name, count in self.top_keys:
            label = name.replace("KEY_", "")[:12]
            bar = _bar(count, max_count, 22)
            lines.append(f"[cyan]{label:<12}[/cyan] [green]{bar}[/green] {count:,}")
        return "\n".join(lines)


class HistoryPanel(Static):
    history: reactive[list] = reactive([])

    def render(self) -> str:
        if not self.history:
            return "[bold]14-day History[/bold]\n\n[dim]No data yet[/dim]"
        max_val = max((r["total"] for r in self.history), default=0)
        spark = "".join(_spark_char(r["total"], max_val) for r in self.history)
        lines = [f"[bold]14-day History[/bold]  [green]{spark}[/green]\n"]
        for r in self.history:
            bar = _bar(r["total"], max_val, 28)
            lines.append(f"[dim]{r['date']}[/dim]  [green]{bar}[/green] {r['total']:,}")
        return "\n".join(lines)


class TapStatsApp(App):
    TITLE = "tapstats"
    CSS = """
    Screen { layout: vertical; background: $surface; }

    #top-row {
        height: auto;
        margin: 1 1 0 1;
    }
    SummaryPanel {
        width: 32;
        padding: 1 2;
        border: round $primary-darken-2;
    }
    TopKeysPanel {
        width: 1fr;
        padding: 1 2;
        margin-left: 1;
        border: round $primary-darken-2;
    }
    HistoryPanel {
        margin: 1;
        padding: 1 2;
        border: round $primary-darken-2;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="top-row"):
            yield SummaryPanel()
            yield TopKeysPanel()
        yield HistoryPanel()
        yield Footer()

    def on_mount(self) -> None:
        self.db = get_db()
        self.action_refresh()
        self.set_interval(5.0, self.action_refresh)

    def action_refresh(self) -> None:
        today = str(date_type.today())
        summary = self.query_one(SummaryPanel)
        top = self.query_one(TopKeysPanel)
        hist = self.query_one(HistoryPanel)

        hist.history = get_history(self.db)

        if RUNTIME_JSON.exists():
            try:
                data = json.loads(RUNTIME_JSON.read_text())
                if data.get("date") == today:
                    summary.today_keys = data["keyboard"]["total"]
                    summary.today_mouse = data["mouse"]
                    top.top_keys = [(name, count) for name, count in data["keyboard"]["top"]]
                    return
            except Exception:
                pass

        db_top = get_top_keys(self.db, today)
        summary.today_keys = sum(r["count"] for r in db_top)
        summary.today_mouse = {}
        top.top_keys = [(r["key_name"], r["count"]) for r in db_top]


def main() -> None:
    TapStatsApp().run()
