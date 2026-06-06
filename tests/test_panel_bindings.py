import asyncio
import sqlite3
from datetime import date, timedelta

from textual.widgets import ContentSwitcher, ListView

from tapstats.db import _init, flush
from tapstats.panel import HistoryView, KeysView, TapStatsApp


def test_page_level_bindings_delegate_from_app():
    async def run():
        app = TapStatsApp()
        async with app.run_test() as pilot:
            await pilot.press("2")
            keys = app.query_one(KeysView)
            assert app.query_one(ContentSwitcher).current == "keys"

            await pilot.press("b")
            assert keys.mode == "bars"

            await pilot.press("a")
            assert keys.scope == "all-time"

            await pilot.press("a")
            assert keys.scope == "day"

            await pilot.press("left")
            assert keys.view_date == str(date.today() - timedelta(days=1))

            await pilot.press("3")
            history = app.query_one(HistoryView)
            assert app.query_one(ContentSwitcher).current == "history"

            await pilot.press("k")
            assert history.mode == "keyboard"

            await pilot.press("m")
            assert history.mode == "mouse"

            await pilot.press("t")
            assert history.mode == "total"

    asyncio.run(run())


def test_history_enter_opens_detail_and_escape_closes_it():
    async def run():
        app = TapStatsApp()
        async with app.run_test() as pilot:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            _init(conn)
            app.db = conn

            target_date = str(date.today() - timedelta(days=1))
            flush(app.db, {"KEY_A": (30, 12)}, {"left": 3}, target_date)
            app.action_refresh()
            await pilot.pause()

            await pilot.press("3")
            history = app.query_one(HistoryView)
            history_list = history.query_one(ListView)
            assert history_list.highlighted_child is not None

            await pilot.press("enter")
            assert history.detail_date == target_date

            await pilot.press("escape")
            assert history.detail_date is None

    asyncio.run(run())
