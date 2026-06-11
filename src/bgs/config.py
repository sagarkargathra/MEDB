from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

BGS_OGC_ITEMS_URL = "https://ogcapi.bgs.ac.uk/collections/world-mineral-statistics/items"

DEFAULT_LIMIT = 5000
DEFAULT_STATISTIC_TYPE = "Production"

DEFAULT_TABLE_FULL = "FullMineralData"
DEFAULT_TABLE_GLOBAL = "BGS_Global"  # keep for compatibility with your manager notebook

@dataclass(frozen=True)
class BGSConfig:
    base_url: str = BGS_OGC_ITEMS_URL
    statistic_type: str = DEFAULT_STATISTIC_TYPE
    limit: int = DEFAULT_LIMIT
    db_path: Path = Path("data") / "World_Mineral_Archive.db"
    table_name: str = DEFAULT_TABLE_FULL
