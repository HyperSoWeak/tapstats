# TUI Redesign — Design Spec

Date: 2026-05-12

## Overview

Redesign `panel.py` from a single-page layout into a 4-tab TUI, add keyboard heatmap visualization, restructure the daemon runtime JSON, and add a `total` display mode to the waybar module.

---

## Views

### Tab 1 — TODAY

- Large "TOTAL ACTIONS" number at top (keystrokes + clicks, scroll excluded)
- Sub-label: `󰌌 12,450 keys  +  󰍽 3,210 clicks`
- Two columns below:
  - **Left — KEYBOARD**: total keystrokes + mini colored bar chart of top 5 keys (quick glance)
  - **Right — MOUSE CLICKS**: left / right / middle counts; scroll shown separately as `±N lines` with a note that it is not counted in total
- Default view when opening the TUI

### Tab 2 — KEYS

- Full QWERTY keyboard heatmap (color intensity = press frequency for the selected date)
- Default date: today; press `←` / `→` to navigate to any previous day
- Press `b` to toggle to colored ranked bar chart (all keys, each key a different color, count labeled inside bar)
- Press `h` to toggle back to heatmap
- Current date shown in header

### Tab 3 — HISTORY

- Sparkline of the past N days at top (configurable via `panel.history_days`)
- One row per day: `date  ████████████  15,660`
  - Rows cycle through a small set of accent colors so adjacent days are visually distinct
- Cursor navigation with `↑` / `↓`; press `Enter` to drill into that day → switches to TODAY view locked to that date (not live), `Escape` returns to HISTORY
- Sub-mode filter: `k` = keyboard only, `m` = mouse clicks only, `t` = total (default)
- Footer: this-week average vs last-week average with delta percentage

### Tab 4 — LIFETIME

- Cumulative total actions since first recorded day (large number, accent color)
- Sub-label: `󰌌 N keys  +  󰍽 N clicks  (since YYYY-MM-DD, N days)`
- Colored bar chart of all-time top keys (same style as Tab 2's bar mode)
- Stats panel: active days / total days, daily average, record single-day count with date

---

## Navigation

| Key | Action |
|-----|--------|
| `1` / `2` / `3` / `4` | Jump to tab |
| `Tab` | Next tab |
| `q` | Quit |
| `r` | Refresh (re-read JSON + DB) |
| `↑` / `↓` | Move cursor (HISTORY) |
| `Enter` | Drill into selected day (HISTORY) |
| `Escape` | Return from drill-down |
| `←` / `→` | Previous / next day (KEYS) |
| `h` | Heatmap mode (KEYS) |
| `b` | Bar chart mode (KEYS) |
| `k` / `m` / `t` | Filter keyboard / mouse / total (HISTORY) |

---

## Total Actions Definition

> **Total Actions = keystrokes + mouse clicks (left + right + middle)**

Scroll wheel (`scroll_up`, `scroll_down`) is **excluded** from all "total" aggregations. It is displayed separately as `±N lines`. Rationale: scroll events fire at a much higher rate than intentional actions and would distort the total.

---

## Database

Schema is unchanged. Two query adjustments:

1. All queries that compute "total" must add `WHERE button NOT IN ('scroll_up', 'scroll_down')` when reading `daily_mouse`.
2. New queries needed:
   - Lifetime keyboard total: `SELECT SUM(count) FROM daily_keys`
   - Lifetime mouse total: `SELECT SUM(count) FROM daily_mouse WHERE button NOT IN ('scroll_up', 'scroll_down')`
   - All-time top keys: `SELECT key_name, SUM(count) as total FROM daily_keys GROUP BY key_name ORDER BY total DESC LIMIT N`

Performance: at ~36,500 rows/year these queries complete in microseconds; no caching layer or summary table needed.

---

## Runtime JSON Restructure

Current flat structure is replaced with two top-level keys:

```json
{
  "today": {
    "date": "2026-05-12",
    "keyboard": { "total": 12450, "top": [["Space", 1820], ["BackSpace", 1240]] },
    "mouse": { "left": 2100, "right": 890, "middle": 220,
               "scroll_up": 2100, "scroll_down": 2130 }
  },
  "lifetime": {
    "total": 4821390,
    "keyboard": 3640210,
    "mouse": 1181180
  }
}
```

**Daemon behavior:**
- On startup: query DB once for lifetime keyboard total and lifetime mouse total (scroll excluded); store in memory as `lifetime_kb` and `lifetime_mouse`.
- On each in-memory increment: add to the lifetime counters as well.
- On each JSON write: emit both `today` and `lifetime` blocks.

All consumers (panel, waybar) must update their read paths from `data["keyboard"]` → `data["today"]["keyboard"]` etc.

---

## Waybar Module

New `display` option: `"total"` (total actions = keystrokes + clicks).

**Config change:** default value of `display` changes from `"keyboard"` to `"total"`.

Updated valid values for `display`: `"keyboard"`, `"mouse"`, `"both"`, `"total"`.

When `display = "total"`: waybar text shows today's total actions count. Tooltip can include lifetime total from `data["lifetime"]["total"]`.

---

## Files to Change

| File | Change |
|------|--------|
| `src/tapstats/panel.py` | Full rewrite: 4-tab app, heatmap widget, drill-down navigation |
| `src/tapstats/db.py` | Add `get_lifetime_totals()`, `get_all_time_top_keys()`, `get_week_totals()` (for week-vs-week); fix scroll exclusion in `get_history()` |
| `src/tapstats/daemon.py` | Load lifetime totals on startup; maintain running lifetime counters; write new JSON structure |
| `src/tapstats/waybar.py` | Update JSON read paths; add `"total"` display mode |
| `src/tapstats/config.py` | Change `WaybarConfig.display` default to `"total"` |
