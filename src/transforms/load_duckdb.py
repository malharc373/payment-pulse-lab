"""Build the DuckDB warehouse from parsed Pulse rows.

Tables are recreated from scratch on each load (the dataset is small and this
guarantees no duplicate rows across re-runs). A ``dim_period`` helper adds a
sortable integer period key so downstream SQL can order quarters correctly.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import duckdb
import pandas as pd

from src import config
from src.ingestion import parsers
from src.ingestion.discover import PulseFile
from src.ingestion.fetch_pulse_data import FetchResult
from src.ingestion.schema import TABLE_COLUMNS

# Explicit column types keep DuckDB from guessing (esp. amount as DOUBLE, not BIGINT).
_TABLE_DDL = {
    "agg_transaction": """
        CREATE TABLE agg_transaction (
            level VARCHAR, geo VARCHAR, year INTEGER, quarter INTEGER,
            category VARCHAR, txn_count BIGINT, txn_amount DOUBLE
        )""",
    "agg_user": """
        CREATE TABLE agg_user (
            level VARCHAR, geo VARCHAR, year INTEGER, quarter INTEGER,
            registered_users BIGINT, app_opens BIGINT
        )""",
    "map_transaction": """
        CREATE TABLE map_transaction (
            state VARCHAR, district VARCHAR, year INTEGER, quarter INTEGER,
            txn_count BIGINT, txn_amount DOUBLE
        )""",
    "map_user": """
        CREATE TABLE map_user (
            state VARCHAR, district VARCHAR, year INTEGER, quarter INTEGER,
            registered_users BIGINT, app_opens BIGINT
        )""",
    "top_transaction": """
        CREATE TABLE top_transaction (
            parent_level VARCHAR, parent_geo VARCHAR, entity_type VARCHAR,
            entity_name VARCHAR, year INTEGER, quarter INTEGER,
            txn_count BIGINT, txn_amount DOUBLE
        )""",
}


def rows_from_results(results: list[FetchResult]) -> tuple[dict[str, list[dict]], list[str]]:
    """Parse every successfully fetched file into per-table row lists.

    Returns ``(table_rows, skipped)`` where ``skipped`` collects human-readable
    notes about files that failed to fetch or parse.
    """
    table_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped: list[str] = []

    for res in results:
        if res.error or res.body is None:
            skipped.append(f"FETCH {res.pf.rel_path}: {res.error or 'empty body'}")
            continue
        try:
            table, rows = parsers.parse(res.pf, res.body)
        except parsers.ParseError as exc:
            skipped.append(f"PARSE {res.pf.rel_path}: {exc}")
            continue
        if table and rows:
            table_rows[table].extend(rows)
    return dict(table_rows), skipped


def load_warehouse(table_rows: dict[str, list[dict]], db_path=None) -> dict[str, int]:
    """(Re)create tables and insert rows. Returns row counts per table."""
    db_path = db_path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    con = duckdb.connect(str(db_path))
    try:
        for table, ddl in _TABLE_DDL.items():
            con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute(ddl)
            rows = table_rows.get(table, [])
            if rows:
                # Order columns explicitly so insert matches the DDL.
                df = pd.DataFrame(rows, columns=TABLE_COLUMNS[table])  # noqa: F841
                con.execute(f"INSERT INTO {table} SELECT * FROM df")
            counts[table] = con.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

        _build_helpers(con)
    finally:
        con.close()
    return counts


def _build_helpers(con: duckdb.DuckDBPyConnection) -> None:
    """Convenience views used throughout the analytics SQL."""
    # Integer period key (e.g. 2023 Q2 -> 20232) for correct chronological sort.
    con.execute("DROP VIEW IF EXISTS state_txn_quarter")
    con.execute(
        """
        CREATE VIEW state_txn_quarter AS
        SELECT
            geo AS state,
            year, quarter,
            year * 10 + quarter AS period_key,
            SUM(txn_count)  AS txn_count,
            SUM(txn_amount) AS txn_amount
        FROM agg_transaction
        WHERE level = 'state'
        GROUP BY geo, year, quarter
        """
    )
    con.execute("DROP VIEW IF EXISTS state_user_quarter")
    con.execute(
        """
        CREATE VIEW state_user_quarter AS
        SELECT
            geo AS state,
            year, quarter,
            year * 10 + quarter AS period_key,
            registered_users,
            app_opens
        FROM agg_user
        WHERE level = 'state'
        """
    )
