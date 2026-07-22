"""Shared synthetic warehouse builder for offline tests (no network, no real data)."""
from __future__ import annotations

from src.transforms.load_duckdb import load_warehouse

STATES = {"karnataka": 1.2e11, "maharashtra": 1.0e11}
CATEGORIES = [("Merchant payments", 1.0), ("Peer-to-peer payments", 3.0),
              ("Recharge & bill payments", 0.2)]
DISTRICTS = {"karnataka": ["bengaluru urban", "mysuru"],
             "maharashtra": ["pune", "mumbai"]}
N_QUARTERS = 14


def build(db_path, with_map: bool = True):
    """Build a small warehouse at ``db_path``.

    ``with_map=False`` mimics PULSE_LIGHT ingestion (aggregated tables only, no
    map/top), so district-grain code paths must degrade gracefully.
    """
    rows = {"agg_transaction": [], "agg_user": [], "map_transaction": [], "map_user": []}
    for state, base in STATES.items():
        amt = base
        for i in range(N_QUARTERS):
            y, q = 2020 + i // 4, i % 4 + 1
            amt *= 1.08
            for cat, mult in CATEGORIES:
                rows["agg_transaction"].append({
                    "level": "state", "geo": state, "year": y, "quarter": q,
                    "category": cat, "txn_count": amt * mult / 1500, "txn_amount": amt * mult})
            rows["agg_user"].append({
                "level": "state", "geo": state, "year": y, "quarter": q,
                "registered_users": 5e6 * (i + 1), "app_opens": 5e7 * (i + 1)})
            if with_map:
                for d in DISTRICTS[state]:
                    rows["map_transaction"].append({
                        "state": state, "district": d, "year": y, "quarter": q,
                        "txn_count": amt / 3000, "txn_amount": amt / 2})
                    rows["map_user"].append({
                        "state": state, "district": f"{d} district", "year": y, "quarter": q,
                        "registered_users": 1e6 * (i + 1), "app_opens": 1e7 * (i + 1)})
    # National rollup for KPI endpoints.
    for i in range(N_QUARTERS):
        y, q = 2020 + i // 4, i % 4 + 1
        for cat, mult in CATEGORIES:
            rows["agg_transaction"].append({
                "level": "country", "geo": "india", "year": y, "quarter": q,
                "category": cat, "txn_count": 1e8 * (i + 1) * mult,
                "txn_amount": 1e11 * (i + 1) * mult})
    load_warehouse(rows, db_path=db_path)
    return db_path
