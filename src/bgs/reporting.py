from __future__ import annotations
from pathlib import Path
import pandas as pd

from .queries import run_query

def inspect_commodity_year_raw(
    db_path: Path,
    *,
    commodity_like: str,
    year: str,
    table: str = "BGS_Global",
) -> pd.DataFrame:
    sql = f"""
    SELECT *
    FROM {table}
    WHERE lower(bgs_commodity_trans) LIKE lower('%{commodity_like}%')
      AND year_clean = '{year}'
    ORDER BY quantity DESC
    """
    return run_query(db_path, sql)

def get_clean_production_report(
    db_path: Path,
    *,
    commodity_like: str,
    table: str = "BGS_Global",
) -> pd.DataFrame:
    sql = f"""
    SELECT
        year_clean AS year,
        country_trans AS country,
        country_iso2_code AS iso_code,
        bgs_statistic_type_trans AS statistic_type,
        bgs_commodity_trans AS commodity,
        bgs_sub_commodity_trans AS sub_commodity,
        quantity,
        units,
        concat_figure_notes_text AS foot_notes
    FROM {table}
    WHERE lower(bgs_commodity_trans) LIKE lower('%{commodity_like}%')
      AND lower(bgs_statistic_type_trans) = 'production'
    ORDER BY year_clean, country_trans
    """
    return run_query(db_path, sql)
