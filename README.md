# World Mineral Archive

This repository builds a local SQLite archive from the BGS World Mineral Statistics OGC API, and provides query utilities to extract clean, analysis ready tables (example: lithium production).

Scope today:

- BGS only (API to SQLite, then reporting queries)
- Not packaged yet (modules live under `src/` and are imported by path)

Planned next:

- Add USGS ingestion in a separate module
- Convert the repo into a proper Python package later

## Requirements

- Python 3.10+ recommended
- `pandas`
- `requests`

If you use Sphinx docs:

- `sphinx`
- `sphinx-autodoc-typehints` (optional)

## Build the BGS archive (script)

From the repo root:

```bash
python scripts/bgs_build_archive.py
````

This creates or extends:

- `data/World_Mineral_Archive.db`
- main table: `FullMineralData` (default)

## Use from notebooks (no packaging)

Add `src/` to the Python path in the notebook:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("..").resolve() / "src"))

from bgs import BGSConfig, build_master_database, get_archive_status, get_clean_production_report
```

Example:

```python
from pathlib import Path

cfg = BGSConfig(db_path=Path("..") / "data" / "World_Mineral_Archive.db")

build_master_database(
    base_url=cfg.base_url,
    db_path=cfg.db_path,
    table_name=cfg.table_name,
    statistic_type=cfg.statistic_type,
    limit=cfg.limit,
)

status = get_archive_status(cfg.db_path)
status
```

## Extract a clean commodity report (example: lithium)

```python
df = get_clean_production_report(
    cfg.db_path,
    commodity_like="Lithium",
    table="BGS_Global",  # change to "FullMineralData" if you use that table as canonical
)
df.head()
```

## Notes on tables

The extractor writes to `FullMineralData`. Some analysis notebooks query `BGS_Global`.
You should choose one canonical table name for BGS and use it consistently.

## License

Add your license file at the repo root. If the code is GPL-3.0, keep `LICENSE` as GPL-3.0.
If you need separate licensing for data, document it explicitly in `docs/`.
