"""Autocomplete and did-you-mean helpers for the tuned search index."""
from __future__ import annotations

import argparse
from typing import Any

from src.common.settings import get_search_client, get_settings

SUGGESTER_NAME = "sg"


def _value(item: Any, *names: str) -> Any:
    for name in names:
        if isinstance(item, dict) and name in item:
            return item[name]
        if hasattr(item, name):
            return getattr(item, name)
    return None


def autocomplete(index_name: str, prefix: str, top: int = 5) -> list[dict[str, str | None]]:
    client = get_search_client(index_name)
    results = client.autocomplete(
        search_text=prefix,
        suggester_name=SUGGESTER_NAME,
        mode="oneTermWithContext",
        use_fuzzy_matching=True,
        top=top,
    )
    return [
        {
            "text": _value(item, "text"),
            "query_plus_text": _value(item, "query_plus_text", "queryPlusText"),
        }
        for item in results
    ]


def did_you_mean(index_name: str, prefix: str, top: int = 5) -> list[dict[str, str | None]]:
    client = get_search_client(index_name)
    results = client.suggest(
        search_text=prefix,
        suggester_name=SUGGESTER_NAME,
        use_fuzzy_matching=True,
        top=top,
        select=["id", "title", "url"],
    )
    return [
        {
            "text": _value(item, "text", "@search.text"),
            "id": _value(item, "id"),
            "title": _value(item, "title"),
            "url": _value(item, "url"),
        }
        for item in results
    ]


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run autocomplete or suggestions against the tuned index.")
    parser.add_argument("prefix", help="Prefix text to complete or suggest from.")
    parser.add_argument("--variant", choices=["baseline", "tuned"], default="tuned")
    parser.add_argument("--kind", choices=["autocomplete", "suggest"], default="autocomplete")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    index_name = settings.index_name(args.variant)
    rows = (
        autocomplete(index_name, args.prefix, args.top)
        if args.kind == "autocomplete"
        else did_you_mean(index_name, args.prefix, args.top)
    )
    if not rows:
        print("No suggestions.")
        return
    for i, row in enumerate(rows, start=1):
        print(f"{i:2}. " + "  ".join(f"{key}={value}" for key, value in row.items() if value))


if __name__ == "__main__":
    main()
