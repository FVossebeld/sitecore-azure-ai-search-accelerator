"""Best-bet curation helpers for deterministic intent routing."""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.common.settings import CONFIG_DIR

BEST_BETS_FILE = CONFIG_DIR / "best_bets.json"


def normalize(text: str) -> str:
    """Normalize query text for curated exact matching."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    chars: list[str] = []
    for ch in without_marks.lower():
        if ch.isalnum() or ch.isspace():
            chars.append(ch)
        else:
            chars.append(" ")
    return " ".join("".join(chars).split())


def _keys_for(text: str) -> set[str]:
    normalized = normalize(text)
    if not normalized:
        return set()
    return {normalized, normalized.replace(" ", "")}


@lru_cache(maxsize=8)
def load_best_bets(path: Path = BEST_BETS_FILE) -> dict[str, dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    index: dict[str, dict[str, Any]] = {}
    for entry in data.get("entries", []):
        if not isinstance(entry, dict):
            continue
        for trigger in entry.get("triggers", []):
            for key in _keys_for(str(trigger)):
                index[key] = entry
    return index


def match_best_bet(query: str, path: Path = BEST_BETS_FILE) -> dict[str, Any] | None:
    index = load_best_bets(path)
    for key in _keys_for(query):
        match = index.get(key)
        if match:
            return match
    return None


def curated_row(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "url": entry.get("url"),
        "score": None,
        "reranker_score": None,
        "curated": True,
        "note": entry.get("note", ""),
    }
