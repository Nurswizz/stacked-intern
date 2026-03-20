import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent / "internships.db"))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        # internships table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS internships (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                company         TEXT NOT NULL,
                role            TEXT NOT NULL,
                location        TEXT,
                apply_link      TEXT,
                simplify_link   TEXT,
                age             TEXT,
                seen_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company, role, apply_link)
            )
        """)
        # subscribers table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id         INTEGER PRIMARY KEY,
                active          INTEGER NOT NULL DEFAULT 1,
                keyword_filter  TEXT,
                joined_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


# ── internship helpers ────────────────────────────────────────────────────────

def upsert_internships(rows: list[dict]) -> list[dict]:
    """Insert new rows; return only those that were actually new."""
    new_entries = []
    with get_conn() as conn:
        for row in rows:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO internships
                    (company, role, location, apply_link, simplify_link, age)
                VALUES
                    (:company, :role, :location, :apply_link, :simplify_link, :age)
                """,
                row,
            )
            if cur.rowcount == 1:
                new_entries.append(row)
        conn.commit()
    return new_entries


def count_internships() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM internships").fetchone()[0]


def get_recent(limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM internships ORDER BY seen_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def search_internships(keyword: str, limit: int = 10) -> list[dict]:
    kw = f"%{keyword}%"
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM internships
            WHERE company LIKE ? OR role LIKE ?
            ORDER BY seen_at DESC
            LIMIT ?
            """,
            (kw, kw, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ── subscriber helpers ────────────────────────────────────────────────────────

def subscribe_user(chat_id: int):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO subscribers (chat_id, active)
            VALUES (?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET active = 1
            """,
            (chat_id,),
        )
        conn.commit()


def unsubscribe_user(chat_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE subscribers SET active = 0 WHERE chat_id = ?", (chat_id,)
        )
        conn.commit()


def set_user_filter(chat_id: int, keyword: str | None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE subscribers SET keyword_filter = ? WHERE chat_id = ?",
            (keyword, chat_id),
        )
        conn.commit()


def get_subscribers() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM subscribers WHERE active = 1"
        ).fetchall()
    return [dict(r) for r in rows]


def get_user(chat_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    return dict(row) if row else None