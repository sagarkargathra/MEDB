from __future__ import annotations
import time
import requests
from typing import Any, Dict, List, Optional

def fetch_page(
    base_url: str,
    *,
    limit: int,
    offset: int,
    statistic_type: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    params = {"f": "json", "limit": limit, "offset": offset}
    if statistic_type:
        params["bgs_statistic_type_trans"] = statistic_type

    r = requests.get(base_url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

def iter_features(
    base_url: str,
    *,
    limit: int,
    statistic_type: Optional[str] = None,
    start_offset: int = 0,
    max_empty_pages: int = 1,
    sleep_s: float = 0.0,
):
    offset = start_offset
    empty_pages = 0

    while True:
        payload = fetch_page(
            base_url,
            limit=limit,
            offset=offset,
            statistic_type=statistic_type,
        )
        features = payload.get("features", []) or []

        if not features:
            empty_pages += 1
            if empty_pages >= max_empty_pages:
                break
        else:
            empty_pages = 0
            for f in features:
                yield f

        offset += limit
        if sleep_s:
            time.sleep(sleep_s)
