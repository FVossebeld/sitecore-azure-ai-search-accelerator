"""Evaluate retrieval quality against a labelled test set.

The test set is a CSV with at least two columns: `query` and `intended_id`
(the id of the document that should be the top result). Metrics are computed
per configuration and written to ./reports.

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
from pathlib import Path
from typing import Any

from src.common.settings import REPORTS_DIR, SAMPLE_TESTSET, get_settings
from src.eval.report import format_table, write_reports
from src.search.query import run_query


def load_testset(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            query = (row.get("query") or "").strip()
            intended = (row.get("intended_id") or row.get("intended_url") or "").strip()
            if query and intended:
                rows.append({"query": query, "intended_id": intended})
    if not rows:
        raise ValueError(f"No usable rows in test set {path} (need 'query' and 'intended_id').")
    return rows


def _rank_of(rows: list[dict[str, Any]], intended_id: str) -> int | None:
    for i, row in enumerate(rows, start=1):
        if str(row.get("id")) == intended_id or str(row.get("url")) == intended_id:
            return i
    return None


def evaluate_config(
    config: str, variant: str, mode: str, testset: list[dict[str, str]], top: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    settings = get_settings()
    index_name = settings.index_name(variant)
    per_query: list[dict[str, Any]] = []

    for case in testset:
        try:
            results = run_query(index_name, case["query"], mode=mode, top=top)
            rank = _rank_of(results, case["intended_id"])
            num = len(results)
        except Exception as exc:  # noqa: BLE001 - record and continue
            print(f"  ! {config} failed on {case['query']!r}: {exc}")
            rank, num = None, 0
        per_query.append(
            {
                "config": config,
                "query": case["query"],
                "intended_id": case["intended_id"],
                "rank": rank,
                "num_results": num,
            }
        )

    n = len(per_query)
    metrics = {
        "config": config,
        "num_queries": n,
        "success_at_1": sum(1 for r in per_query if r["rank"] == 1) / n,
        "success_at_3": sum(1 for r in per_query if r["rank"] and r["rank"] <= 3) / n,
        "mrr_at_10": sum(1 / r["rank"] for r in per_query if r["rank"] and r["rank"] <= 10) / n,
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
    args = parser.parse_args()

    # Default behaviour is the full comparison. Passing --variant or --mode
    # explicitly switches to evaluating that single configuration.
    import sys

    explicit_single = any(a in sys.argv for a in ("--variant", "--mode"))
    compare = args.compare or not explicit_single

    testset = load_testset(args.testset)
    print(f"Loaded {len(testset)} test queries from {args.testset}\n")

    configs = build_configs(compare, args.variant, args.mode, settings.enable_vector)
    all_metrics: list[dict[str, Any]] = []
    all_per_query: list[dict[str, Any]] = []
    for config, variant, mode in configs:
        print(f"Evaluating {config} ...")
        metrics, per_query = evaluate_config(config, variant, mode, testset, args.top)
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
