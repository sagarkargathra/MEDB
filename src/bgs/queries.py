from __future__ import annotations
from pathlib import Path
import pandas as pd

from .db import connect

def run_query(db_path: Path, sql: str) -> pd.DataFrame:
    conn = connect(db_path)
    try:
        return pd.read_sql(sql, conn)
    finally:
        conn.close()

def get_archive_status(db_path: Path) -> pd.DataFrame:
    conn = connect(db_path)
    try:
        tables = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
            conn,
        )["name"].tolist()

        rows = []
        for t in tables:
            if t == "sqlite_sequence":
                continue
            n = pd.read_sql(f"SELECT COUNT(*) AS n FROM {t}", conn)["n"].iloc[0]
            rows.append({"table": t, "rows": int(n)})
        return pd.DataFrame(rows)
    finally:
        conn.close()

def get_table_columns(db_path: Path, table: str) -> pd.DataFrame:
    return run_query(db_path, f"PRAGMA table_info({table})")
