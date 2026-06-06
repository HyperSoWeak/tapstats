# tapstats

Track daily keyboard and mouse activity. Shows live stats in Waybar and a 3-tab analytics TUI.

Built for Wayland — reads input directly via `evdev`. All data is stored locally in SQLite and never deleted.

## Requirements

- Arch Linux (or any distro with `evdev` support)
- Python 3.11+
- User in the `input` group (see [Setup](#setup))
- Waybar (optional)

## Installation

### Via AUR

```bash
paru -S tapstats-git
```

### Via makepkg

```bash
git clone https://github.com/HyperSoWeak/tapstats
cd tapstats
makepkg -si
```

Installs binaries to `/usr/bin/` and the systemd service to `/usr/lib/systemd/user/`.

### From source (development)

```bash
git clone https://github.com/HyperSoWeak/tapstats
cd tapstats
uv pip install -e .
```

Scripts are available via `uv run tapstats`, `uv run tapstats-daemon`, `uv run tapstats-waybar`.

## Setup

### 1. Join the `input` group

Required for the daemon to read from `/dev/input/`.

```bash
sudo usermod -aG input $USER
```

Log out and back in for this to take effect.

### 2. Enable the daemon

```bash
systemctl --user enable --now tapstats
```

Check status and logs:

```bash
systemctl --user status tapstats
journalctl --user -u tapstats -f
```

## TUI

```bash
tapstats
```

Three tabs, navigate with `1`–`3` or `Tab`:

| Tab | Content |
|-----|---------|
| **OVERVIEW** | Today total, keyboard/click/scroll summary, top keys, 7-day trend, lifetime summary |
| **KEYS** | QWERTY heatmap or ranked bars; `←`/`→` navigate days; `a` toggles day/all-time; `b` bars; `h` heatmap |
| **HISTORY** | 7-day and 30-day trends, records, daily list, in-tab day detail; `k`/`m`/`t` filter keyboard / mouse / total |

Other keys: `Enter` drill into a selected history day, `Esc` return from detail, `r` refresh, `q` quit.

## Waybar

Add to `~/.config/waybar/config.jsonc`:

```jsonc
"modules-right": ["custom/tapstats", ...],

"custom/tapstats": {
  "exec": "tapstats-waybar",
  "return-type": "json",
  "signal": 8,
  "tooltip": true,
  "on-click": "kitty tapstats"
}
```

Then restart Waybar:

```bash
systemctl --user restart waybar
```

The module updates every 5 seconds via signal. Hover to see today's top keys, mouse breakdown, and all-time total.

When `display = "total"`, the module uses a single total icon instead of combining the keyboard and mouse icons.

## Configuration

`~/.config/tapstats/config.toml` — all fields are optional, defaults shown below.

```toml
[daemon]
tick_interval = 5      # seconds between Waybar updates and SQLite flush check
flush_interval = 30    # seconds between SQLite writes

[waybar]
signal = 8             # Waybar signal number (RTMIN+N), must match config.jsonc
display = "total"      # "total" | "keyboard" | "mouse" | "both"
compact = true         # true → "󰌌 󰍽 1.2k"  /  false → "󰌌 󰍽 1,234"
top_keys_count = 5     # number of keys shown in the tooltip

[panel]
history_days = 14      # days of history shown in the HISTORY tab

[db]
path = "~/.local/share/tapstats/stats.db"
```

## Data

All history is kept in SQLite at `~/.local/share/tapstats/stats.db`. The `history_days` setting only affects what the TUI displays — nothing is ever deleted.

Scroll wheel events (`scroll_up`, `scroll_down`) are recorded but excluded from all action totals. They are shown separately as lines scrolled.

Useful queries:

```sql
-- All-time top keys
SELECT key_name, SUM(count) AS total
FROM daily_keys
GROUP BY key_name
ORDER BY total DESC
LIMIT 20;

-- Single day breakdown
SELECT key_name, count
FROM daily_keys
WHERE date = '2026-05-11'
ORDER BY count DESC;

-- Daily totals for the past 30 days
SELECT date, SUM(count) AS total
FROM daily_keys
GROUP BY date
ORDER BY date DESC
LIMIT 30;
```
