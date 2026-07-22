"""Tests for the loader + data-quality checks against a tiny in-memory warehouse."""
from __future__ import annotations

import duckdb
import pytest

from src.transforms import quality_checks
from src.transforms.load_duckdb import load_warehouse


def _clean_rows():
    """Two states x two quarters x one category = a balanced, valid panel."""
    agg_txn, agg_user = [], []
    for state, base in (("karnataka", 100), ("maharashtra", 200)):
        for i, (y, q) in enumerate([(2023, 1), (2023, 2)]):
            agg_txn.append({
                "level": "state", "geo": state, "year": y, "quarter": q,
                "category": "Merchant payments",
                "txn_count": base + i, "txn_amount": (base + i) * 10.0,
            })
            agg_user.append({
                "level": "state", "geo": state, "year": y, "quarter": q,
                "registered_users": base * 5, "app_opens": base * 50,
            })
    # National rows so the state-vs-national ratio check has a denominator.
    for i, (y, q) in enumerate([(2023, 1), (2023, 2)]):
        total = (100 + i) * 10.0 + (200 + i) * 10.0
        agg_txn.append({
            "level": "country", "geo": "india", "year": y, "quarter": q,
            "category": "Merchant payments",
            "txn_count": 300 + 2 * i, "txn_amount": total,
        })
    return {"agg_transaction": agg_txn, "agg_user": agg_user}


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "test.duckdb"
    yield path


def test_clean_warehouse_passes_all_checks(db):
    counts = load_warehouse(_clean_rows(), db_path=db)
    assert counts["agg_transaction"] == 6
    results = quality_checks.run_checks(db_path=db)
    assert not quality_checks.has_failures(results)
    by_name = {r.name: r for r in results}
    assert by_name["panel completeness"].status == quality_checks.PASS
    assert by_name["state vs national total"].status == quality_checks.PASS


def test_duplicate_grain_fails(db):
    rows = _clean_rows()
    rows["agg_transaction"].append(dict(rows["agg_transaction"][0]))  # exact dup
    load_warehouse(rows, db_path=db)
    results = quality_checks.run_checks(db_path=db)
    dup = next(r for r in results if r.name == "unique transaction grain")
    assert dup.status == quality_checks.FAIL


def test_negative_metric_fails(db):
    rows = _clean_rows()
    rows["agg_transaction"][0]["txn_amount"] = -1.0
    load_warehouse(rows, db_path=db)
    results = quality_checks.run_checks(db_path=db)
    neg = next(r for r in results if r.name == "no negative txn metrics")
    assert neg.status == quality_checks.FAIL


def test_panel_gap_warns(db):
    rows = _clean_rows()
    # Drop maharashtra 2023 Q2 -> unbalanced panel.
    rows["agg_transaction"] = [
        r for r in rows["agg_transaction"]
        if not (r["geo"] == "maharashtra" and r["quarter"] == 2)
    ]
    load_warehouse(rows, db_path=db)
    results = quality_checks.run_checks(db_path=db)
    gap = next(r for r in results if r.name == "panel completeness")
    assert gap.status == quality_checks.WARN


def test_helper_views_exist(db):
    load_warehouse(_clean_rows(), db_path=db)
    con = duckdb.connect(str(db), read_only=True)
    try:
        n = con.execute("SELECT COUNT(*) FROM state_txn_quarter").fetchone()[0]
        assert n == 4  # 2 states x 2 quarters
    finally:
        con.close()
