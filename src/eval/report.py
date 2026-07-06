"""Render evaluation results as a console table, a markdown report, and CSV files."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

METRIC_COLUMNS = [
    ("success_at_1", "Success@1"),
    ("success_at_3", "Success@3"),
    ("mrr_at_10", "MRR@10"),
    ("ndcg_at_10", "NDCG@10"),
    ("found_rate", "Found@10"),
    ("zero_result_rate", "Zero-result"),
]


def _fmt(value: float) -> str:
    return f"{value * 100:5.1f}%"


def format_table(metrics: list[dict[str, Any]]) -> str:
    header = f"{'Configuration':<22}" + "".join(f"{label:>13}" for _, label in METRIC_COLUMNS)
    lines = [header, "-" * len(header)]
    for m in metrics:
        row = f"{m['config']:<22}" + "".join(f"{_fmt(m[key]):>13}" for key, _ in METRIC_COLUMNS)
        lines.append(row)
    return "\n".join(lines)


def write_reports(
    metrics: list[dict[str, Any]],
    per_query: list[dict[str, Any]],
    out_dir: Path,
    baseline_config: str | None = None,
) -> tuple[Path, Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "relevance-report.md"
    summary_csv = out_dir / "relevance-summary.csv"
    detail_csv = out_dir / "relevance-per-query.csv"

    # Summary CSV.
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["config", *[key for key, _ in METRIC_COLUMNS], "num_queries"])
        for m in metrics:
            writer.writerow([m["config"], *[f"{m[key]:.4f}" for key, _ in METRIC_COLUMNS], m["num_queries"]])

    # Per-query CSV.
    with detail_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["config", "query", "intended_id", "rank", "num_results", "ndcg_at_10"])
        for r in per_query:
            writer.writerow(
                [
                    r["config"],
                    r["query"],
                    r["intended_id"],
                    r["rank"] if r["rank"] else "",
                    r["num_results"],
                    f"{r.get('ndcg_at_10', 0.0):.4f}",
                ]
            )

    # Markdown report.
    lines = ["# Relevance evaluation", ""]
    lines.append("| Configuration | " + " | ".join(label for _, label in METRIC_COLUMNS) + " |")
    lines.append("|" + "---|" * (len(METRIC_COLUMNS) + 1))
    for m in metrics:
        cells = " | ".join(_fmt(m[key]) for key, _ in METRIC_COLUMNS)
        lines.append(f"| {m['config']} | {cells} |")
    lines.append("")

    if baseline_config:
        base = next((m for m in metrics if m["config"] == baseline_config), None)
        best = max(metrics, key=lambda m: m["success_at_1"])
        if base and best["config"] != baseline_config:
            delta = (best["success_at_1"] - base["success_at_1"]) * 100
            lines.append(
                f"**Lift:** Success@1 improves from {_fmt(base['success_at_1']).strip()} "
                f"({baseline_config}) to {_fmt(best['success_at_1']).strip()} "
                f"({best['config']}), a gain of {delta:+.1f} points."
            )
            lines.append("")

    lines.append("## Metric definitions")
    lines.append("")
    lines.append("- **Success@1**: share of queries where the intended page is the first result.")
    lines.append("- **Success@3**: share where the intended page is in the top 3.")
    lines.append("- **MRR@10**: mean reciprocal rank of the intended page within the top 10.")
    lines.append("- **NDCG@10**: normalized discounted cumulative gain over the top 10, using graded relevance labels 0 to 3; rewards putting the most relevant pages highest.")
    lines.append("- **Found@10**: share where the intended page appears anywhere in the top 10.")
    lines.append("- **Zero-result**: share of queries that returned no results at all.")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, summary_csv, detail_csv
