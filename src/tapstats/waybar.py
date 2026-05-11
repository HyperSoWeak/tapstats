import json
import os
from datetime import date as date_type
from pathlib import Path

from .config import get_config
from ._util import fmt_compact as _fmt

RUNTIME_JSON = Path(f"/run/user/{os.getuid()}/tapstats.json")
_FALLBACK = json.dumps({"text": "󰌌 —", "tooltip": "tapstats not running"})


def _format_output(data: dict, cfg) -> str | None:
    today = data.get("today", {})
    if today.get("date") != str(date_type.today()):
        return None

    kb = today.get("keyboard", {}).get("total", 0)
    mouse = today.get("mouse", {})
    clicks = mouse.get("left", 0) + mouse.get("right", 0) + mouse.get("middle", 0)
    lifetime_total = data.get("lifetime", {}).get("total", 0)

    fmt = _fmt if cfg.waybar.compact else lambda n: f"{n:,}"

    match cfg.waybar.display:
        case "total":
            text = f"󰌌 󰍽 {fmt(kb + clicks)}"
        case "both":
            text = f"󰌌 {fmt(kb)}  󰍽 {fmt(clicks)}"
        case "mouse":
            text = f"󰍽 {fmt(clicks)}"
        case _:
            text = f"󰌌 {fmt(kb)}"

    n = cfg.waybar.top_keys_count
    top_lines = "\n".join(
        f"  {name.replace('KEY_', ''):<10} {count:,}"
        for name, count in today.get("keyboard", {}).get("top", [])[:n]
    )

    tooltip = (
        f"TAPSTATS  {today.get('date', '')}\n\n"
        f"KEYBOARD  {kb:,}\n"
        f"{top_lines}\n\n"
        f"MOUSE\n"
        f"  Left {mouse.get('left', 0):,}  Right {mouse.get('right', 0):,}  Middle {mouse.get('middle', 0):,}\n"
        f"  Scroll ↑ {mouse.get('scroll_up', 0):,}  ↓ {mouse.get('scroll_down', 0):,}\n\n"
        f"LIFETIME  {lifetime_total:,}"
    )

    return json.dumps({"text": text, "tooltip": tooltip})


def main() -> None:
    if not RUNTIME_JSON.exists():
        print(_FALLBACK)
        return
    try:
        data = json.loads(RUNTIME_JSON.read_text())
    except Exception:
        print(_FALLBACK)
        return

    cfg = get_config()
    result = _format_output(data, cfg)
    print(result if result is not None else _FALLBACK)
