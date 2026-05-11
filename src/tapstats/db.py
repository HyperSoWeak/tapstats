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
    """keys: {key_name: (key_code, count)}, mouse: {button: count}"""
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


def get_top_keys(conn: sqlite3.Connection, date: str, limit: int = 15) -> list[dict]:
    rows = conn.execute(
        "SELECT key_name, count FROM daily_keys WHERE date = ? ORDER BY count DESC LIMIT ?",
        (date, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_history(conn: sqlite3.Connection, days: int = 14) -> list[dict]:
    rows = conn.execute(
        """
        WITH combined AS (
            SELECT date, count FROM daily_keys
            UNION ALL
            SELECT date, count FROM daily_mouse
        )
        SELECT date, SUM(count) AS total
        FROM combined
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        (days,),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]
