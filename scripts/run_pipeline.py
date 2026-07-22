"""End-to-end ingestion pipeline: discover -> fetch -> parse -> load -> validate.

Usage:
    python -m scripts.run_pipeline               # default scope from config/.env
    python -m scripts.run_pipeline --min-year 2022 --max-year 2023
    python -m scripts.run_pipeline --datasets aggregated map   # skip 'top'
"""
from __future__ import annotations

import argparse
import sys
import time

from src import config
from src.ingestion import discover, parsers
from src.ingestion.fetch_pulse_data import fetch_all
from src.transforms import quality_checks
from src.transforms.load_duckdb import load_warehouse, rows_from_results


def _progress(i: int, total: int) -> None:
    if i == total or i % 100 == 0:
        pct = 100 * i / total
        print(f"\r  fetched {i}/{total} ({pct:4.0f}%)", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the Pulse ingestion pipeline.")
    ap.add_argument("--min-year", type=int, default=config.MIN_YEAR)
    ap.add_argument("--max-year", type=int, default=config.MAX_YEAR)
    ap.add_argument(
        "--datasets", nargs="+", default=list(config.DEFAULT_DATASETS),
        choices=["aggregated", "map", "top"],
        help="dataset families to ingest (default respects PULSE_LIGHT)",
    )
    args = ap.parse_args(argv)

    t0 = time.time()
    print(f"[1/4] Discovering files ({args.min_year}-{args.max_year}, {args.datasets})...")
    all_files = discover.discover_files(
        datasets=tuple(args.datasets), min_year=args.min_year, max_year=args.max_year
    )
    files = [f for f in all_files if parsers.is_ingested(f)]
    print(f"      {len(all_files)} discovered, {len(files)} ingested files to fetch.")
    if not files:
        print("No files matched the requested scope.", file=sys.stderr)
        return 1

    print("[2/4] Fetching (cached under data/raw/)...")
    results = fetch_all(files, progress=_progress)
    print()
    cached = sum(r.from_cache for r in results)
    errs = sum(bool(r.error) for r in results)
    print(f"      {len(results)} done | {cached} from cache | {errs} errors")

    print("[3/4] Parsing & loading into DuckDB...")
    table_rows, skipped = rows_from_results(results)
    counts = load_warehouse(table_rows)
    for table, n in counts.items():
        print(f"      {table:18} {n:>8,} rows")
    if skipped:
        print(f"      {len(skipped)} files skipped (first 5):")
        for s in skipped[:5]:
            print(f"        - {s}")

    print("[4/4] Data-quality checks...")
    checks = quality_checks.run_checks()
    print(quality_checks.format_report(checks))

    print(f"\nDone in {time.time() - t0:.1f}s -> {config.DB_PATH}")
    return 1 if quality_checks.has_failures(checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
