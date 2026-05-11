# tapstats

Track how many times you press each key and click your mouse. Displays live stats in Waybar and a dashboard TUI.

Works on Wayland via `evdev`. Data is stored in SQLite and never deleted.

## Requirements

- Arch Linux (or any distro with `evdev`)
- Python 3.11+
- Waybar (optional)
- User must be in the `input` group

---

## Installation

### Via AUR

```bash
paru -S tapstats-git
```

### Via makepkg (local)

```bash
git clone https://github.com/USERNAME/tapstats
cd tapstats
makepkg -si
```

This builds a proper Arch package and installs binaries to `/usr/bin/` and the systemd service to `/usr/lib/systemd/user/`.

### From source (development)

```bash
git clone https://github.com/USERNAME/tapstats
cd tapstats
uv pip install -e .
```

Scripts are installed to `.venv/bin/`. Use `uv run tapstats` / `uv run tapstats-daemon`.

---

## Setup

### 1. Join the `input` group

```bash
sudo usermod -aG input $USER
```

Log out and back in for this to take effect.

### 2. Start the daemon

**One-off (for testing):**

```bash
uv run tapstats-daemon
# or
.venv/bin/tapstats-daemon
```

**As a systemd user service (permanent):**

```bash
systemctl --user enable --now tapstats
```

Check logs:

```bash
journalctl --user -u tapstats -f
```

---

## TUI

```bash
uv run tapstats
```

```
┏━ TAPSTATS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 2026-05-11    ⌨  4,521    🖱  234                               ┃
┠─────────────────────────┰────────────────────────────────────────┨
┃ KEYBOARD                ┃ TOP KEYS                               ┃
┃   Total         4,521   ┃ Space       ████████████████████  812  ┃
┃                         ┃ E           █████████████         601  ┃
┃ MOUSE                   ┃ Backspace   ██████████            489  ┃
┃   Left            234   ┃ ...                                    ┃
┠─────────────────────────┸────────────────────────────────────────┨
┃ 14 DAYS  ▁▂▁▃▅▇▆▄▂▅▇▆▅▄                                        ┃
┃ 2026-04-28  ████████████                    2,341               ┃
┃ 2026-04-29  ██████████████████              3,891               ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

Keybindings: `r` refresh, `q` quit.

---

## Waybar

Add to your Waybar config:

```json
"modules-right": ["custom/tapstats"],

"custom/tapstats": {
    "exec": "tapstats-waybar",
    "return-type": "json",
    "signal": 8
}
```

Optional CSS (`style.css`):

```css
#custom-tapstats {
    padding: 0 8px;
}
```

Restart Waybar:

```bash
systemctl --user restart waybar
```

The module updates every second. Hover for a tooltip with today's top keys and mouse breakdown.

---

## Configuration

Config file location: `~/.config/tapstats/config.toml`

The file is optional — all values have defaults.

```toml
[daemon]
tick_interval = 1      # seconds between Waybar updates
flush_interval = 30    # seconds between SQLite writes

[waybar]
signal = 8             # Waybar signal number (RTMIN+N)
top_keys_count = 5     # keys shown in Waybar tooltip
display = "keyboard"   # what to show: "keyboard", "mouse", "both"

[panel]
history_days = 14      # days shown in TUI history chart

[db]
path = "~/.local/share/tapstats/stats.db"
```

The full history in SQLite is never pruned regardless of `history_days`.

---

## Data

SQLite database at `~/.local/share/tapstats/stats.db`.

```sql
-- Query all-time top keys
SELECT key_name, SUM(count) AS total
FROM daily_keys
GROUP BY key_name
ORDER BY total DESC
LIMIT 20;

-- Query a specific day
SELECT key_name, count FROM daily_keys
WHERE date = '2026-05-11'
ORDER BY count DESC;
```
