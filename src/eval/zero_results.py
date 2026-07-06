"""Mine local query telemetry for zero-result and low-result patterns."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.common.settings import REPORTS_DIR
from src.search.telemetry import QUERY_LOG_PATH

DEFAULT_OUT = REPORTS_DIR / "zero-results.md"


def _read_log(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError:
                print(f"Skipping malformed JSONL line {line_no}")
    return rows


def _top(counter: Counter[str], limit: int = 10) -> list[tuple[str, int]]:
    return counter.most_common(limit)


def write_report(rows: list[dict[str, Any]], threshold: int, out_path: Path) -> tuple[Counter[str], Counter[str]]:
    zero = Counter(str(row.get("query", "")).strip() for row in rows if int(row.get("num_results", 0)) == 0)
    low = Counter(
        str(row.get("query", "")).strip()
        for row in rows
        if 0 < int(row.get("num_results", 0)) < threshold
    )
    zero.pop("", None)
    low.pop("", None)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Zero-result and low-result query mining",
        "",
        "Each zero-result query is a vocabulary, content, or configuration gap. Triage each pattern into synonyms, best-bets, or new content.",
        "",
        f"Total logged queries: {len(rows)}",
        f"Zero-result unique queries: {len(zero)}",
        f"Low-result unique queries below threshold {threshold}: {len(low)}",
        "",
        "## Zero-result queries",
        "",
    ]
    if zero:
        lines.append("| Query | Count |")
        lines.append("| --- | --- |")
        for query, count in zero.most_common():
            lines.append(f"| {query} | {count} |")
    else:
        lines.append("No zero-result queries logged.")
    lines.extend(["", "## Low-result queries", ""])
    if low:
        lines.append("| Query | Count |")
        lines.append("| --- | --- |")
        for query, count in low.most_common():
            lines.append(f"| {query} | {count} |")
    else:
        lines.append("No low-result queries logged.")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return zero, low


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate local query logs for zero-result mining.")
    parser.add_argument("--log", type=Path, default=QUERY_LOG_PATH)
    parser.add_argument("--threshold", type=int, default=3)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.log.exists():
        print(f"No query log found at {args.log}. Run query.py with CLI logging first, or pass --log.")
        return

    rows = _read_log(args.log)
    zero, low = write_report(rows, args.threshold, args.out)
    print(f"Total logged queries: {len(rows)}")
    print("Top zero-result queries:")
    for query, count in _top(zero):
        print(f"  {count}  {query}")
    if not zero:
        print("  none")
    print("Top low-result queries:")
    for query, count in _top(low):
        print(f"  {count}  {query}")
    if not low:
        print("  none")
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
