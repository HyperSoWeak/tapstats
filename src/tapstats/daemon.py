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
        lt = get_lifetime_totals(self.db)
        today_kb = sum(today_data["keys"].values())
        today_clicks = sum(
            v for k, v in today_data["mouse"].items()
            if k not in ("scroll_up", "scroll_down")
        )
        # Subtract today's already-committed portion to avoid double-counting when we add live today totals at write time.
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
