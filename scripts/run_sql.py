"""Execute a .sql analytics file against the warehouse, printing each result.

Usage:
    python -m scripts.run_sql src/analytics/kpis.sql
    python -m scripts.run_sql src/analytics/growth_analysis.sql --limit 8
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from src import config


def split_statements(sql: str) -> list[tuple[str, str]]:
    """Split into (raw_block, executable_body) pairs at true statement ends.

    Statement boundaries are ';' in *code*, not in ``--`` comments, so a
    semicolon inside a comment can't split a query. The raw block keeps the
    comment lines (used for titles); the body strips them for execution.
    """
    out: list[tuple[str, str]] = []
    raw_lines: list[str] = []
    for line in sql.splitlines():
        raw_lines.append(line)
        code = line.split("--", 1)[0]  # portion before any line comment
        if ";" in code:
            raw_block = "\n".join(raw_lines)
            body = "\n".join(
                ln for ln in raw_block.splitlines()
                if ln.strip() and not ln.strip().startswith("--")
            ).replace(";", "").strip()
            if body:
                out.append((raw_block, body))
            raw_lines = []
    return out


def _title(raw_block: str) -> str:
    for ln in raw_block.splitlines():
        s = ln.strip()
        if s.startswith("--") and any(c.isalnum() for c in s):
            return s.lstrip("- ").rstrip("- ")
    return "query"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql_file", type=Path)
    ap.add_argument("--limit", type=int, default=10, help="rows to print per query")
    args = ap.parse_args(argv)

    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        for raw, body in split_statements(args.sql_file.read_text()):
            print(f"\n=== {_title(raw)} ===")
            df = con.execute(body).df()
            with_pd_opts(df, args.limit)
    finally:
        con.close()
    return 0


def with_pd_opts(df, limit: int) -> None:
    import pandas as pd

    with pd.option_context("display.max_columns", None, "display.width", 120):
        print(df.head(limit).to_string(index=False))
        if len(df) > limit:
            print(f"... ({len(df)} rows total)")


if __name__ == "__main__":
    raise SystemExit(main())
