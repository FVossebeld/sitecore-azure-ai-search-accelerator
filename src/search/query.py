"""Query helpers for the three retrieval modes.

- keyword:  plain full-text search (BM25). Works on any index.
- semantic: full-text retrieval reranked by the semantic ranker. Needs the tuned
            index (it holds the semantic configuration).
- hybrid:   keyword plus vector, fused with Reciprocal Rank Fusion, then reranked.
            Needs the tuned index built with ENABLE_VECTOR=true.
"""
from __future__ import annotations

import argparse
from typing import Any

from src.common.settings import get_search_client, get_settings
from src.config.index_schema import VECTOR_FIELD

SELECT_FIELDS = ["id", "title", "url", "contentType"]


def _rows(results) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in results:
        rows.append(
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "url": r.get("url"),
                "score": r.get("@search.score"),
                "reranker_score": r.get("@search.reranker_score"),
            }
        )
    return rows


def keyword_search(index_name: str, query: str, top: int = 10) -> list[dict[str, Any]]:
    client = get_search_client(index_name)
    results = client.search(search_text=query, top=top, query_type="simple", select=SELECT_FIELDS)
    return _rows(results)


def semantic_search(index_name: str, query: str, top: int = 10) -> list[dict[str, Any]]:
    settings = get_settings()
    client = get_search_client(index_name)
    results = client.search(
        search_text=query,
        top=top,
        query_type="semantic",
        semantic_configuration_name=settings.semantic_config_name,
        select=SELECT_FIELDS,
    )
    return _rows(results)


def hybrid_search(index_name: str, query: str, top: int = 10) -> list[dict[str, Any]]:
    from azure.search.documents.models import VectorizedQuery

    from src.common.embeddings import embed_texts

    settings = get_settings()
    vector = embed_texts(settings, [query])[0]
    vector_query = VectorizedQuery(
        vector=vector, k_nearest_neighbors=top, fields=VECTOR_FIELD
    )
    client = get_search_client(index_name)
    results = client.search(
        search_text=query,
        vector_queries=[vector_query],
        top=top,
        query_type="semantic",
        semantic_configuration_name=settings.semantic_config_name,
        select=SELECT_FIELDS,
    )
    return _rows(results)


def run_query(index_name: str, query: str, mode: str = "keyword", top: int = 10) -> list[dict[str, Any]]:
    mode = mode.lower()
    if mode == "keyword":
        return keyword_search(index_name, query, top)
    if mode == "semantic":
        return semantic_search(index_name, query, top)
    if mode == "hybrid":
        return hybrid_search(index_name, query, top)
    raise ValueError(f"Unknown mode: {mode!r} (expected keyword, semantic, or hybrid)")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run an ad-hoc query against an index.")
    parser.add_argument("query", help="The search text.")
    parser.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="semantic")
    parser.add_argument("--variant", choices=["baseline", "tuned"], default="tuned")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    index_name = settings.index_name(args.variant)
    rows = run_query(index_name, args.query, mode=args.mode, top=args.top)
    print(f"Query: {args.query!r}  mode={args.mode}  index={index_name}\n")
    if not rows:
        print("No results.")
        return
    for i, row in enumerate(rows, start=1):
        score = row.get("reranker_score") or row.get("score")
        print(f"{i:2}. {row['title']}  (score={score:.3f})")
        print(f"    {row['url']}")


if __name__ == "__main__":
    main()
