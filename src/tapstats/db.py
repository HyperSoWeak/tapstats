import sqlite3
from datetime import date as date_type
from pathlib import Path


def get_db() -> sqlite3.Connection:
    from .config import get_config
    path = Path(get_config().db.path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS daily_keys (
            date     TEXT NOT NULL,
            key_code INTEGER NOT NULL,
            key_name TEXT NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, key_code)
        );
        CREATE TABLE IF NOT EXISTS daily_mouse (
            date   TEXT NOT NULL,
            button TEXT NOT NULL,
            count  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (date, button)
        );
    """)
    conn.commit()


def load_today(conn: sqlite3.Connection) -> dict:
    today = str(date_type.today())
    keys = {
        row["key_name"]: row["count"]
        for row in conn.execute(
            "SELECT key_name, count FROM daily_keys WHERE date = ?", (today,)
        )
    }
    mouse = {
        row["button"]: row["count"]
        for row in conn.execute(
            "SELECT button, count FROM daily_mouse WHERE date = ?", (today,)
        )
    }
    return {"keys": keys, "mouse": mouse}


def flush(
    conn: sqlite3.Connection,
    keys: dict[str, tuple[int, int]],
    mouse: dict[str, int],
    today: str,
) -> None:
    with conn:
        for name, (code, count) in keys.items():
            conn.execute(
                """
                INSERT INTO daily_keys (date, key_code, key_name, count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (date, key_code) DO UPDATE SET count = count + excluded.count
                """,
                (today, code, name, count),
            )
        for button, count in mouse.items():
            conn.execute(
                """
                INSERT INTO daily_mouse (date, button, count)
                VALUES (?, ?, ?)
                ON CONFLICT (date, button) DO UPDATE SET count = count + excluded.count
                """,
                (today, button, count),
            )


def get_top_keys(conn: sqlite3.Connection, date: str, limit: int | None = 15) -> list[dict]:
    if limit is None:
        rows = conn.execute(
            "SELECT key_name, count FROM daily_keys WHERE date = ? ORDER BY count DESC",
            (date,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT key_name, count FROM daily_keys WHERE date = ? ORDER BY count DESC LIMIT ?",
            (date, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_history(conn: sqlite3.Connection, days: int = 14, mode: str = "total") -> list[dict]:
    if mode == "keyboard":
        sql = """
            SELECT date, SUM(count) AS total FROM daily_keys
            GROUP BY date ORDER BY date DESC LIMIT ?
        """
    elif mode == "mouse":
        sql = """
            SELECT date, SUM(count) AS total FROM daily_mouse
            WHERE button NOT IN ('scroll_up', 'scroll_down')
            GROUP BY date ORDER BY date DESC LIMIT ?
        """
    else:
        sql = """
            WITH combined AS (
                SELECT date, count FROM daily_keys
                UNION ALL
                SELECT date, count FROM daily_mouse
                WHERE button NOT IN ('scroll_up', 'scroll_down')
            )
            SELECT date, SUM(count) AS total FROM combined
            GROUP BY date ORDER BY date DESC LIMIT ?
        """
    rows = conn.execute(sql, (days,)).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_lifetime_totals(conn: sqlite3.Connection) -> dict:
    kb = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM daily_keys"
    ).fetchone()[0]
    mouse = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM daily_mouse WHERE button NOT IN ('scroll_up', 'scroll_down')"
    ).fetchone()[0]
    return {"keyboard": kb, "mouse": mouse, "total": kb + mouse}


def get_lifetime_stats(conn: sqlite3.Connection) -> dict:
    totals = get_lifetime_totals(conn)

    row = conn.execute("""
        SELECT MIN(date) AS first_date, COUNT(DISTINCT date) AS active_days
        FROM (SELECT date FROM daily_keys UNION SELECT date FROM daily_mouse)
    """).fetchone()

    record_row = conn.execute("""
        WITH combined AS (
            SELECT date, count FROM daily_keys
            UNION ALL
            SELECT date, count FROM daily_mouse
            WHERE button NOT IN ('scroll_up', 'scroll_down')
        )
        SELECT date, SUM(count) AS total FROM combined
        GROUP BY date ORDER BY total DESC LIMIT 1
    """).fetchone()

    return {
        **totals,
        "first_date": row["first_date"] or str(date_type.today()),
        "active_days": row["active_days"] or 0,
        "record_date": record_row["date"] if record_row else "",
        "record_total": record_row["total"] if record_row else 0,
    }


def get_all_time_top_keys(conn: sqlite3.Connection, limit: int = 20) -> list[tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT key_name, SUM(count) AS total FROM daily_keys
        GROUP BY key_name ORDER BY total DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [(r["key_name"], r["total"]) for r in rows]


def get_week_totals(conn: sqlite3.Connection) -> tuple[int, int]:
    row = conn.execute("""
        WITH combined AS (
            SELECT date, count FROM daily_keys
            UNION ALL
            SELECT date, count FROM daily_mouse
            WHERE button NOT IN ('scroll_up', 'scroll_down')
        ), daily AS (
            SELECT date, SUM(count) AS total FROM combined GROUP BY date
        )
        SELECT
            COALESCE(SUM(CASE WHEN date >= date('now', '-6 days') THEN total ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN date >= date('now', '-13 days') AND date < date('now', '-6 days') THEN total ELSE 0 END), 0)
        FROM daily
    """).fetchone()
    return (row[0], row[1])


def get_day_stats(conn: sqlite3.Connection, date: str, top_limit: int = 15) -> dict:
    kb_total = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM daily_keys WHERE date = ?", (date,)
    ).fetchone()[0]
    top_keys = [(r["key_name"], r["count"]) for r in get_top_keys(conn, date, top_limit)]
    mouse = {
        row["button"]: row["count"]
        for row in conn.execute(
            "SELECT button, count FROM daily_mouse WHERE date = ?", (date,)
        )
    }
    return {"keyboard_total": kb_total, "top_keys": top_keys, "mouse": mouse}
