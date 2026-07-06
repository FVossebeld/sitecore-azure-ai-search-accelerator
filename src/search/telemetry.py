"""Local JSONL query telemetry for offline relevance loops."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.settings import REPORTS_DIR

QUERY_LOG_PATH = Path(os.environ.get("QUERY_LOG_PATH", REPORTS_DIR / "query-log.jsonl"))


def log_query(
    query: str,
    index_name: str,
    mode: str,
    num_results: int,
    top_ids: list[Any],
    curated: bool = False,
    fallback: str | None = None,
) -> None:
    try:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "index": index_name,
            "mode": mode,
            "num_results": int(num_results),
            "top_ids": [str(item) for item in top_ids[:5]],
            "curated": bool(curated),
            "fallback": fallback,
        }
        QUERY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with QUERY_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return
