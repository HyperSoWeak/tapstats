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


def main() -> None:
    if not RUNTIME_JSON.exists():
        print(_FALLBACK)
        return

    try:
        data = json.loads(RUNTIME_JSON.read_text())
    except Exception:
        print(_FALLBACK)
        return

    if data.get("date") != str(date_type.today()):
        print(_FALLBACK)
        return

    cfg = get_config()
    kb = data["keyboard"]["total"]
    mouse = data["mouse"]
    clicks = mouse.get("left", 0) + mouse.get("right", 0) + mouse.get("middle", 0)

    fmt = _fmt if cfg.waybar.compact else lambda n: f"{n:,}"

    match cfg.waybar.display:
        case "both":
            text = f"󰌌 {fmt(kb)}  󰍽 {fmt(clicks)}"
        case "mouse":
            text = f"󰍽 {fmt(clicks)}"
        case _:
            text = f"󰌌 {fmt(kb)}"

    n = cfg.waybar.top_keys_count
    top_lines = "\n".join(
        f"  {name.replace('KEY_', ''):<10} {count:,}"
        for name, count in data["keyboard"]["top"][:n]
    )

    tooltip = (
        f"TAPSTATS  {data['date']}\n\n"
        f"KEYBOARD  {kb:,}\n"
        f"{top_lines}\n\n"
        f"MOUSE\n"
        f"  Left {mouse.get('left', 0):,}  Right {mouse.get('right', 0):,}  Middle {mouse.get('middle', 0):,}\n"
        f"  Scroll ↑ {mouse.get('scroll_up', 0):,}  ↓ {mouse.get('scroll_down', 0):,}"
    )

    print(json.dumps({"text": text, "tooltip": tooltip}))
