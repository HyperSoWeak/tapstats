import json
import os
from datetime import date as date_type
from pathlib import Path

from .config import get_config

RUNTIME_JSON = Path(f"/run/user/{os.getuid()}/tapstats.json")

_FALLBACK = json.dumps({"text": "⌨ —  🖱 —", "tooltip": "tapstats not running"})


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

    kb = data["keyboard"]["total"]
    mouse = data["mouse"]
    clicks = mouse.get("left", 0) + mouse.get("right", 0) + mouse.get("middle", 0)

    n = get_config().waybar.top_keys_count
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

    print(json.dumps({"text": f"⌨ {kb:,}  🖱 {clicks:,}", "tooltip": tooltip}))
