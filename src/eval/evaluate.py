"""Evaluate retrieval quality against a labelled test set.

The test set is a CSV with at least two columns: `query` and `intended_id`
(the id of the document that should be the top result). An optional `relevance`
column supports graded judgments from 0 to 3. Metrics are computed per
configuration and written to ./reports.

By default it compares four configurations so you can see where the lift comes
from:

    baseline-keyword  naive index, plain full-text search
    tuned-keyword     relevance config (analyzer, synonyms, scoring), full-text
    tuned-semantic    relevance config plus the semantic ranker
    tuned-hybrid      adds vector + RRF (only when ENABLE_VECTOR=true)
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.common.settings import REPORTS_DIR, SAMPLE_TESTSET, get_settings
from src.eval.report import format_table, write_reports
from src.search.query import run_query


def _parse_relevance(value: str | None) -> int:
    if value is None or value.strip() == "":
        return 3
    relevance = int(value)
    if relevance < 0 or relevance > 3:
        raise ValueError(f"relevance must be 0 to 3, got {value!r}")
    return relevance


def load_testset(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            query = (row.get("query") or "").strip()
            intended = (row.get("intended_id") or row.get("intended_url") or "").strip()
            if query and intended:
                rows.append(
                    {
                        "query": query,
                        "intended_id": intended,
                        "relevance": _parse_relevance(row.get("relevance")),
                    }
                )
    if not rows:
        raise ValueError(f"No usable rows in test set {path} (need 'query' and 'intended_id').")
    return rows


def _grade_for(row_or_id: Any, grade_map: dict[str, int]) -> int:
    if isinstance(row_or_id, dict):
        for key in (row_or_id.get("id"), row_or_id.get("url")):
            if key is not None and str(key) in grade_map:
                return grade_map[str(key)]
        return 0
    return grade_map.get(str(row_or_id), 0)


def _rank_of_first_relevant(rows: list[dict[str, Any]], grade_map: dict[str, int]) -> int | None:
    for i, row in enumerate(rows, start=1):
        if _grade_for(row, grade_map) >= 1:
            return i
    return None


def ndcg_at_k(ranked_ids: list[Any], grade_map: dict[str, int], k: int = 10) -> float:
    def gain(grade: int) -> float:
        return float((2**grade) - 1)

    dcg = 0.0
    for position, item in enumerate(ranked_ids[:k], start=1):
        grade = _grade_for(item, grade_map)
        dcg += gain(grade) / math.log2(position + 1)

    ideal_grades = sorted((grade for grade in grade_map.values() if grade > 0), reverse=True)[:k]
    idcg = sum(gain(grade) / math.log2(position + 1) for position, grade in enumerate(ideal_grades, start=1))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def _group_testset(testset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in testset:
        grouped[row["query"]].append(row)
    return [{"query": query, "judgments": judgments} for query, judgments in grouped.items()]


def _grade_map(judgments: list[dict[str, Any]]) -> dict[str, int]:
    grades: dict[str, int] = {}
    for judgment in judgments:
        intended = str(judgment["intended_id"])
        grades[intended] = max(grades.get(intended, 0), int(judgment["relevance"]))
    return grades


def _representative_intended_id(judgments: list[dict[str, Any]]) -> str:
    best = max(judgments, key=lambda row: (int(row["relevance"]), str(row["intended_id"])))
    return str(best["intended_id"])


def evaluate_config(
    config: str,
    variant: str,
    mode: str,
    testset: list[dict[str, Any]],
    top: int,
    curated: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    settings = get_settings()
    index_name = settings.index_name(variant)
    per_query: list[dict[str, Any]] = []

    for case in _group_testset(testset):
        grade_map = _grade_map(case["judgments"])
        try:
            results = run_query(index_name, case["query"], mode=mode, top=top, curated=curated)
            rank = _rank_of_first_relevant(results, grade_map)
            ndcg = ndcg_at_k(results, grade_map, 10)
            num = len(results)
        except Exception as exc:  # noqa: BLE001 - record and continue
            print(f"  ! {config} failed on {case['query']!r}: {exc}")
            rank, ndcg, num = None, 0.0, 0
        per_query.append(
            {
                "config": config,
                "query": case["query"],
                "intended_id": _representative_intended_id(case["judgments"]),
                "rank": rank,
                "num_results": num,
                "ndcg_at_10": ndcg,
            }
        )

    n = len(per_query)
    metrics = {
        "config": config,
        "num_queries": n,
        "success_at_1": sum(1 for r in per_query if r["rank"] == 1) / n,
        "success_at_3": sum(1 for r in per_query if r["rank"] and r["rank"] <= 3) / n,
        "mrr_at_10": sum(1 / r["rank"] for r in per_query if r["rank"] and r["rank"] <= 10) / n,
        "ndcg_at_10": sum(float(r["ndcg_at_10"]) for r in per_query) / n,
        "found_rate": sum(1 for r in per_query if r["rank"] is not None) / n,
        "zero_result_rate": sum(1 for r in per_query if r["num_results"] == 0) / n,
    }
    return metrics, per_query


def build_configs(compare: bool, variant: str, mode: str, enable_vector: bool) -> list[tuple[str, str, str]]:
    if not compare:
        return [(f"{variant}-{mode}", variant, mode)]
    configs = [
        ("baseline-keyword", "baseline", "keyword"),
        ("tuned-keyword", "tuned", "keyword"),
        ("tuned-semantic", "tuned", "semantic"),
    ]
    if enable_vector:
        configs.append(("tuned-hybrid", "tuned", "hybrid"))
    return configs


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality against a test set.")
    parser.add_argument("--testset", type=Path, default=SAMPLE_TESTSET)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--compare", action="store_true", help="Compare baseline and tuned configurations (default).")
    parser.add_argument("--variant", choices=["baseline", "tuned"], default="tuned")
    parser.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="semantic")
    parser.add_argument("--report-dir", type=Path, default=REPORTS_DIR)
    parser.add_argument(
        "--curated",
        action="store_true",
        help="Include deterministic best-bet curation. Default metrics measure the ranker only.",
    )
    args = parser.parse_args()

    # Default behaviour is the full comparison. Passing --variant or --mode
    # explicitly switches to evaluating that single configuration.
    import sys

    explicit_single = any(a in sys.argv for a in ("--variant", "--mode"))
    compare = args.compare or not explicit_single

    testset = load_testset(args.testset)
    print(f"Loaded {len(testset)} test judgments from {args.testset}\n")
    if args.curated:
        print("Curation enabled: best-bets are measured as a deterministic layer.\n")

    configs = build_configs(compare, args.variant, args.mode, settings.enable_vector)
    all_metrics: list[dict[str, Any]] = []
    all_per_query: list[dict[str, Any]] = []
    for config, variant, mode in configs:
        print(f"Evaluating {config} ...")
        metrics, per_query = evaluate_config(config, variant, mode, testset, args.top, curated=args.curated)
        all_metrics.append(metrics)
        all_per_query.extend(per_query)

    print("\n" + format_table(all_metrics) + "\n")

    baseline_config = "baseline-keyword" if compare else None
    md_path, summary_csv, detail_csv = write_reports(
        all_metrics, all_per_query, args.report_dir, baseline_config=baseline_config
    )
    print(f"Report written to {md_path}")
    print(f"Summary CSV:      {summary_csv}")
    print(f"Per-query CSV:    {detail_csv}")


if __name__ == "__main__":
    main()
