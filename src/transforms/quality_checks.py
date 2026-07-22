"""Post-load data-quality checks against the DuckDB warehouse.

Each check returns a :class:`CheckResult`. A check can be ``PASS``, ``WARN``
(a data quirk worth surfacing but not a pipeline failure), or ``FAIL`` (a
schema/integrity violation that should block downstream use). The runner prints
a report and exits non-zero if any check FAILs, so it works in CI.
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb

from src import config

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def _scalar(con, sql: str):
    return con.execute(sql).fetchone()[0]


def run_checks(db_path=None) -> list[CheckResult]:
    db_path = db_path or config.DB_PATH
    con = duckdb.connect(str(db_path), read_only=True)
    results: list[CheckResult] = []
    try:
        # 1. Core fact table is non-empty.
        n = _scalar(con, "SELECT COUNT(*) FROM agg_transaction")
        results.append(
            CheckResult("agg_transaction non-empty", PASS if n else FAIL, f"{n} rows")
        )

        # 2. No negative counts or amounts anywhere they'd be nonsensical.
        neg = _scalar(
            con,
            "SELECT COUNT(*) FROM agg_transaction "
            "WHERE txn_count < 0 OR txn_amount < 0",
        )
        results.append(
            CheckResult("no negative txn metrics", PASS if neg == 0 else FAIL, f"{neg} bad rows")
        )

        # 3. No null keys in the fact table.
        nullkeys = _scalar(
            con,
            "SELECT COUNT(*) FROM agg_transaction "
            "WHERE geo IS NULL OR year IS NULL OR quarter IS NULL OR category IS NULL",
        )
        results.append(
            CheckResult("no null keys", PASS if nullkeys == 0 else FAIL, f"{nullkeys} rows")
        )

        # 4. Grain uniqueness: one row per (level, geo, year, quarter, category).
        dups = _scalar(
            con,
            """
            SELECT COUNT(*) FROM (
                SELECT level, geo, year, quarter, category, COUNT(*) c
                FROM agg_transaction
                GROUP BY 1,2,3,4,5 HAVING COUNT(*) > 1
            )
            """,
        )
        results.append(
            CheckResult("unique transaction grain", PASS if dups == 0 else FAIL, f"{dups} dup groups")
        )

        # 5. Quarters are in the valid 1-4 range.
        badq = _scalar(
            con, "SELECT COUNT(*) FROM agg_transaction WHERE quarter NOT BETWEEN 1 AND 4"
        )
        results.append(
            CheckResult("quarter in 1..4", PASS if badq == 0 else FAIL, f"{badq} rows")
        )

        # 6. Panel completeness: warn if any state is missing quarters that its
        #    peers report (gaps break lag features and forecasting downstream).
        gaps = con.execute(
            """
            WITH periods AS (SELECT DISTINCT period_key FROM state_txn_quarter),
                 states  AS (SELECT DISTINCT state FROM state_txn_quarter),
                 grid    AS (SELECT state, period_key FROM states CROSS JOIN periods),
                 have    AS (SELECT state, period_key FROM state_txn_quarter)
            SELECT g.state, COUNT(*) AS missing
            FROM grid g LEFT JOIN have h USING (state, period_key)
            WHERE h.period_key IS NULL
            GROUP BY g.state ORDER BY missing DESC
            """
        ).fetchall()
        if gaps:
            top = ", ".join(f"{s}({m})" for s, m in gaps[:5])
            results.append(
                CheckResult("panel completeness", WARN, f"{len(gaps)} states with gaps: {top}")
            )
        else:
            results.append(CheckResult("panel completeness", PASS, "balanced panel"))

        # 7. Consistency: state totals should be within a sane band of the
        #    national aggregate (they won't match exactly, but shouldn't be wild).
        ratio = _scalar(
            con,
            """
            SELECT COALESCE(
              (SELECT SUM(txn_amount) FROM agg_transaction WHERE level='state')
              / NULLIF((SELECT SUM(txn_amount) FROM agg_transaction WHERE level='country'), 0),
            0)
            """,
        )
        status = PASS if 0.8 <= ratio <= 1.2 else WARN
        results.append(
            CheckResult("state vs national total", status, f"state/national = {ratio:.3f}")
        )
    finally:
        con.close()
    return results


def format_report(results: list[CheckResult]) -> str:
    lines = ["Data-quality report", "-" * 60]
    for r in results:
        lines.append(f"[{r.status:4}] {r.name:32} {r.detail}")
    n_fail = sum(r.status == FAIL for r in results)
    n_warn = sum(r.status == WARN for r in results)
    lines.append("-" * 60)
    lines.append(f"{len(results)} checks | {n_fail} FAIL | {n_warn} WARN")
    return "\n".join(lines)


def has_failures(results: list[CheckResult]) -> bool:
    return any(r.status == FAIL for r in results)
