from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(db_path))

def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    q = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
    cur = conn.execute(q, (table,))
    return cur.fetchone() is not None

def add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    coltype: str = "TEXT",
) -> None:
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()

def create_index(
    conn: sqlite3.Connection,
    *,
    table: str,
    index: str,
    column: str,
) -> None:
    conn.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({column})")
    conn.commit()

def count_rows(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cur.fetchone()[0])

def ensure_table_has_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: Iterable[str],
    *,
    default_type: str = "TEXT",
) -> None:
    """
    Ensure `table` has at least the given columns. Adds missing columns as TEXT.

    SQLite does not support adding multiple columns at once, so we iterate.
    """
    cur = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}  # row[1] is column name

    for col in columns:
        if col not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN "{col}" {default_type}')
    conn.commit()
