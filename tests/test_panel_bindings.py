import asyncio
from datetime import date, timedelta

from textual.widgets import ContentSwitcher

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
