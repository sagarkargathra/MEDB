from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from .client import iter_features
from .db import connect, create_index, add_column_if_missing, ensure_table_has_columns


def _features_to_df(features) -> pd.DataFrame:
    rows = [f.get("properties", {}) for f in features]
    df = pd.DataFrame(rows)

    if "year" in df.columns:
        df["year_clean"] = df["year"].astype(str).str.slice(0, 4)
    elif "year_clean" not in df.columns:
        df["year_clean"] = None

    return df


def build_master_database(
    *,
    base_url: str,
    db_path: Path,
    table_name: str,
    statistic_type: Optional[str] = "Production",
    limit: int = 5000,
    start_offset: int = 0,
    sleep_s: float = 0.0,
) -> Tuple[Path, int]:
    """
    Build or extend a local SQLite archive from the BGS OGC API.

    Returns
    -------
    (db_path, rows_written)
    """
    conn = connect(db_path)
    rows_written = 0

    # Determine once whether the table already exists
    table_exists = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )

    batch: list[dict] = []
    for feature in iter_features(
        base_url,
        limit=limit,
        statistic_type=statistic_type,
        start_offset=start_offset,
        sleep_s=sleep_s,
    ):
        batch.append(feature)

        if len(batch) >= limit:
            df = _features_to_df(batch)

            # If table exists, align schema before append (prevents 'no column named ...')
            if table_exists:
                ensure_table_has_columns(conn, table_name, df.columns)

            df.to_sql(table_name, conn, if_exists="append", index=False)
            table_exists = True  # table definitely exists after first write

            rows_written += len(df)
            batch = []

    if batch:
        df = _features_to_df(batch)
        if table_exists:
            ensure_table_has_columns(conn, table_name, df.columns)
        df.to_sql(table_name, conn, if_exists="append", index=False)
        table_exists = True
        rows_written += len(df)

    # Defensive schema patch (kept from your notebook intent)
    add_column_if_missing(conn, table_name, "shape", "TEXT")

    # Indexes for common filters
    create_index(conn, table=table_name, index="idx_mineral_group", column="erml_group")
    create_index(conn, table=table_name, index="idx_year_clean", column="year_clean")

    conn.close()
    return db_path, rows_written


def is_api_empty_at_offset(
    *,
    base_url: str,
    limit: int,
    offset: int,
    statistic_type: Optional[str] = "Production",
) -> bool:
    from .client import fetch_page

    payload = fetch_page(
        base_url,
        limit=limit,
        offset=offset,
        statistic_type=statistic_type,
    )
    features = payload.get("features", []) or []
    return len(features) == 0
