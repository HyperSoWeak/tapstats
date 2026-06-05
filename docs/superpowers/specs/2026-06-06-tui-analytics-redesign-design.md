# TUI Analytics Redesign — Design Spec

Date: 2026-06-06

## Overview

Redesign the Textual panel from the current 4-tab layout into a 3-tab analytics TUI:

- `OVERVIEW`: today-first dashboard with live totals and compact analytics.
- `KEYS`: keyboard-focused heatmap and ranking analysis.
- `HISTORY`: trend-focused time analysis with daily drill-down.

The redesign changes the information architecture and panel layout only. It does not change the database schema, daemon runtime JSON format, or Waybar behavior. New database work is limited to read-only helper queries.

## Goals

- Open the TUI and answer "How much have I used today?" within one glance.
- Keep keyboard analysis separate from time-series analysis.
- Remove the standalone `LIFETIME` tab and surface lifetime stats where they are useful.
- Make the interface feel more like an analytics dashboard while staying practical in a terminal.
- Preserve existing keyboard-driven navigation.

## Non-Goals

- No GUI app.
- No schema migration.
- No daemon or Waybar redesign.
- No new persistence or cache layer.
- No unrelated refactor outside the panel and query helpers needed by the panel.

## Information Architecture

### Tabs

| Key | Tab | Purpose |
|-----|-----|---------|
| `1` | `OVERVIEW` | Today-first summary and compact analytics |
| `2` | `KEYS` | Keyboard heatmap, ranking, date/scope analysis |
| `3` | `HISTORY` | Trends, comparisons, records, daily list, drill-down |

`LIFETIME` is removed as a tab. Lifetime totals move into `OVERVIEW`; all-time key analysis moves into `KEYS`.

## Global Navigation

| Key | Action |
|-----|--------|
| `1` / `2` / `3` | Jump to tab |
| `Tab` | Next tab |
| `q` | Quit |
| `r` | Refresh |
| `Esc` | Exit drill-down or local detail mode |

The tab bar should use compact labels:

```text
  1 OVERVIEW   2 KEYS   3 HISTORY
```

Active tab remains visually distinct with reverse/bold styling.

## View 1 — OVERVIEW

`OVERVIEW` is the default view. It is a focused dashboard: the largest visual element is today's total actions, with secondary panels for the main analytics.

### Layout

```text
  1 OVERVIEW   2 KEYS   3 HISTORY

  TODAY
  12,450 actions
  keys 9,800  clicks 2,650  scroll ±4,230

  Top Keys Today              7-Day Trend
  SPACE  █████████ 1,820      ▁▂▅▆█▃▄
  E      █████      940       this 7d 82,100  +12.4%
  A      ████       810       avg/day 11,728

  Mouse Today                 Lifetime
  left 1,900  right 620       total 2.4M
  middle 130  scroll ±4,230   avg/day 8,420
                               record 18,200  2026-05-31
```

### Data

- Today keyboard total: runtime JSON when current, DB fallback.
- Today mouse clicks: left + right + middle; scroll excluded from total.
- Today scroll: `scroll_up + scroll_down`, displayed separately.
- Top keys today: existing `top_keys` data.
- 7-day trend: existing `get_history(..., days=7, mode="total")`.
- Week comparison: existing `get_week_totals()`.
- Lifetime: existing `get_lifetime_stats()`, merged with current runtime JSON when the runtime file contains today's data.

### Behavior

- Refresh every 5 seconds, matching the existing panel.
- Manual `r` refresh remains available.
- No drill-down from `OVERVIEW`; the view stays scan-focused.
- If the terminal is narrow, stack panels vertically in this order:
  1. Today
  2. Top Keys Today
  3. 7-Day Trend
  4. Mouse Today
  5. Lifetime

## View 2 — KEYS

`KEYS` owns all keyboard-specific analysis.

### Default State

- Scope: selected date, default today.
- Mode: heatmap.
- Date navigation: `←` previous day, `→` next day, never beyond today.

### Modes

| Key | Mode |
|-----|------|
| `h` | Heatmap |
| `b` | Ranked bars |
| `a` | Toggle selected date vs all-time |

### Layout — Date Heatmap

```text
  KEYS  today  heatmap  scope: day

  ESC  F1 F2 F3 F4   F5 F6 F7 F8   F9 F10 F11 F12
  `  1  2  3  4  5  6  7  8  9  0  -  =  BKSP
  TAB  Q  W  E  R  T  Y  U  I  O  P  [  ]  \
  CAPS  A  S  D  F  G  H  J  K  L  ;  '  RET
  SHFT  Z  X  C  V  B  N  M  ,  .  /  SHFT
  CTL SYS ALT       SPACE       ALT SYS MNU CTL

  low ░░▒▒▓▓██ high
```

### Layout — Ranked Bars

```text
  KEYS  today  bars  scope: day

  SPACE       ████████████████████ 1,820
  E           ██████████            940
  A           ████████              810
  BACKSPACE   █████                 520
```

### All-Time Scope

When `a` toggles to all-time:

- Heatmap uses all-time key totals from a new read-only helper.
- Bars use existing `get_all_time_top_keys()`.
- Date navigation is disabled or ignored.
- Header shows `scope: all-time`.

### Data

- Date scope heatmap/bars: existing `get_top_keys(conn, date, limit=None)`.
- All-time bars: existing `get_all_time_top_keys()`.
- All-time heatmap: add `get_all_time_keys(conn)` to return all key totals.

This helper is read-only and does not change schema.

## View 3 — HISTORY

`HISTORY` owns trend and time-series analysis. It should feel less like a plain list and more like a compact analytics page.

### Modes

| Key | Mode |
|-----|------|
| `t` | Total actions |
| `k` | Keyboard |
| `m` | Mouse clicks |

### Layout

```text
  HISTORY  total

  Trend
  7d  ▁▂▅▆█▃▄  82,100  +12.4%
  30d ▁▁▂▃▄▆█▅▃▂▃▄▅▇█...  avg/day 10,420

  Records
  best day   18,200  2026-05-31
  low day     2,340  2026-05-22
  active days 28/30

  Daily
  2026-06-06  ████████████████  12,450
  2026-06-05  ███████████       8,900
  2026-06-04  █████████████     10,300
```

### Drill-Down

Pressing `Enter` on a highlighted day opens a local detail mode inside `HISTORY`, instead of switching to `OVERVIEW`.

```text
  HISTORY  2026-06-05 detail

  Total 8,900
  keys 7,200  clicks 1,700  scroll ±3,120

  Top Keys
  SPACE  █████████ 1,420
  E      █████      760

  Mouse
  left 1,230  right 390  middle 80
```

`Esc` returns to the normal history list.

### Data

- 7-day trend: `get_history(conn, 7, mode)`.
- 30-day trend: `get_history(conn, 30, mode)`.
- Daily list: configurable `panel.history_days`, using existing config.
- Week comparison: existing `get_week_totals()` for total mode.
- Week and previous-week comparison for all modes: add `get_period_totals(conn, days, mode)` or extend `get_week_totals()` to accept `mode`.
- Records: add `get_history_summary(conn, days, mode)`.

The helper returns best day, low day, active days, total, and daily average for the requested window.

## Visual Style

- Keep the terminal palette restrained with a few accents from the existing color set.
- Use strong hierarchy through placement and labels, not decorative borders everywhere.
- Prefer aligned rows and compact headers.
- Keep charts character-based: bars and sparklines remain Rich/Textual text widgets.
- Use icons only where already established and readable in Nerd Font environments.
- Avoid dense help text inside each view; use footer bindings for discoverability.

## Responsiveness

The panel should be usable in common terminal sizes:

- Wide: two-column overview panels.
- Medium: narrower two-column panels, shorter bars.
- Narrow: single-column stacked sections.

No text should rely on fixed wide labels that overflow at normal terminal widths.

## Implementation Scope

Primary file:

- `src/tapstats/panel.py`

Likely supporting file:

- `src/tapstats/db.py` for read-only analytics helpers.

Tests:

- Existing helper tests for `_bar`, `_heat_level`, `_spark_char`, `_compact` remain valid.
- Add focused tests for any new DB helpers.
- If view logic is split into pure formatting helpers, add tests for those helpers.

Documentation:

- Update `README.md` TUI section after implementation.

## Acceptance Criteria

- Running `tapstats` opens `OVERVIEW`.
- Tab navigation uses `1`, `2`, `3`, and `Tab`.
- `OVERVIEW` shows today total, keyboard total, click total, scroll, top keys, 7-day trend, and lifetime summary.
- `KEYS` defaults to today heatmap and supports heatmap/bars plus day/all-time scope.
- `HISTORY` shows trend analytics, mode filters, daily list, and in-tab day detail drill-down.
- Scroll remains excluded from total actions everywhere.
- Existing daemon JSON and Waybar behavior continue unchanged.
- Tests pass.
