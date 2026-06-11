from pathlib import Path
import sys

# Allow imports without packaging
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bgs import BGSConfig, build_master_database, is_api_empty_at_offset

def main() -> None:
    cfg = BGSConfig(db_path=Path("data") / "World_Mineral_Archive.db")

    db_path, n = build_master_database(
        base_url=cfg.base_url,
        db_path=cfg.db_path,
        table_name=cfg.table_name,
        statistic_type=cfg.statistic_type,
        limit=cfg.limit,
    )
    print(f"DB: {db_path}")
    print(f"Rows written: {n}")

    empty = is_api_empty_at_offset(
        base_url=cfg.base_url,
        limit=cfg.limit,
        offset=408480,  # keep your current audit value
        statistic_type=cfg.statistic_type,
    )
    print(f"API empty at audit offset: {empty}")

if __name__ == "__main__":
    main()
