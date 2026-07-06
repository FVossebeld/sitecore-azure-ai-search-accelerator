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
from src.search import telemetry
from src.search.curation import curated_row, match_best_bet

SELECT_FIELDS = ["id", "title", "url", "contentType"]
LUCENE_SPECIAL_CHARS = set('+-!(){}[]^"~*?:\\/&|')


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
                "curated": False,
            }
        )
    return rows


def _escape_lucene(term: str) -> str:
    return "".join(f"\\{ch}" if ch in LUCENE_SPECIAL_CHARS else ch for ch in term)


def _fuzzify(query: str, min_len: int = 4, max_edits: int = 1) -> str:
    parts: list[str] = []
    for token in query.split():
        if token.isupper() or any(ch.isdigit() for ch in token):
            parts.append(token)
        elif token.isalpha() and len(token) >= min_len:
            parts.append(f"{_escape_lucene(token)}~{max_edits}")
        else:
            parts.append(_escape_lucene(token))
    return " ".join(parts)


def keyword_search(index_name: str, query: str, top: int = 10, fuzzy: bool = False) -> list[dict[str, Any]]:
    client = get_search_client(index_name)
    if fuzzy:
        results = client.search(
            search_text=_fuzzify(query),
            top=top,
            query_type="full",
            search_mode="any",
            select=SELECT_FIELDS,
        )
    else:
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


def _base_query(index_name: str, query: str, mode: str, top: int) -> list[dict[str, Any]]:
    if mode == "keyword":
        return keyword_search(index_name, query, top)
    if mode == "semantic":
        return semantic_search(index_name, query, top)
    if mode == "hybrid":
        return hybrid_search(index_name, query, top)
    raise ValueError(f"Unknown mode: {mode!r} (expected keyword, semantic, or hybrid)")


def run_query(
    index_name: str,
    query: str,
    mode: str = "keyword",
    top: int = 10,
    curated: bool = True,
    log: bool = False,
) -> list[dict[str, Any]]:
    mode = mode.lower()
    pinned_entry = match_best_bet(query) if curated else None
    pinned = curated_row(pinned_entry) if pinned_entry else None
    fallback_used: str | None = None

    rows = _base_query(index_name, query, mode, top)
    if not rows and mode in {"keyword", "semantic"}:
        try:
            rows = keyword_search(index_name, query, top, fuzzy=True)
            fallback_used = "fuzzy"
            for row in rows:
                row["fallback"] = "fuzzy"
        except Exception:
            rows = []

    if pinned:
        pinned_id = pinned.get("id")
        rows = [row for row in rows if row.get("id") != pinned_id]
        rows = [pinned, *rows][:top]
    else:
        rows = rows[:top]

    if log:
        try:
            telemetry.log_query(
                query=query,
                index_name=index_name,
                mode=mode,
                num_results=len(rows),
                top_ids=[row.get("id") for row in rows if row.get("id")],
                curated=bool(pinned),
                fallback=fallback_used,
            )
        except Exception:
            pass
    return rows


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run an ad-hoc query against an index.")
    parser.add_argument("query", help="The search text.")
    parser.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="semantic")
    parser.add_argument("--variant", choices=["baseline", "tuned"], default="tuned")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--no-curation", action="store_true", help="Disable best-bet curation.")
    args = parser.parse_args()

    index_name = settings.index_name(args.variant)
    rows = run_query(
        index_name,
        args.query,
        mode=args.mode,
        top=args.top,
        curated=not args.no_curation,
        log=True,
    )
    fallback_note = " (fuzzy fallback)" if any(row.get("fallback") == "fuzzy" for row in rows) else ""
    print(f"Query: {args.query!r}  mode={args.mode}  index={index_name}{fallback_note}\n")
    if not rows:
        print("No results.")
        return
    for i, row in enumerate(rows, start=1):
        score = row.get("reranker_score") or row.get("score")
        score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "n/a"
        prefix = "[PINNED] " if row.get("curated") else ""
        print(f"{i:2}. {prefix}{row['title']}  (score={score_text})")
        print(f"    {row['url']}")
        if row.get("note"):
            print(f"    {row['note']}")


if __name__ == "__main__":
    main()
