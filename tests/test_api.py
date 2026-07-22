"""Smoke tests for the FastAPI layer, backed by a tiny synthetic warehouse.

We build a small DuckDB from fixture rows, point the service at it, and exercise
the routes with FastAPI's TestClient — no network, no real data required.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.transforms.load_duckdb import load_warehouse


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Build a synthetic warehouse with enough history for the SQL endpoints.
    rows = {"agg_transaction": [], "agg_user": []}
    for s, base in (("karnataka", 1e11), ("maharashtra", 1.2e11)):
        amt = base
        for i in range(12):
            y, q = 2021 + i // 4, i % 4 + 1
            amt *= 1.1
            rows["agg_transaction"].append({
                "level": "state", "geo": s, "year": y, "quarter": q,
                "category": "Merchant payments", "txn_count": amt / 1500, "txn_amount": amt})
            rows["agg_transaction"].append({
                "level": "state", "geo": s, "year": y, "quarter": q,
                "category": "Peer-to-peer payments", "txn_count": amt / 3000, "txn_amount": amt * 3})
            rows["agg_user"].append({
                "level": "state", "geo": s, "year": y, "quarter": q,
                "registered_users": 1e7 * (i + 1), "app_opens": 1e8 * (i + 1)})
    # National rollup for category-mix / trend endpoints.
    for i in range(12):
        y, q = 2021 + i // 4, i % 4 + 1
        for cat, mult in (("Merchant payments", 1.0), ("Peer-to-peer payments", 3.0)):
            rows["agg_transaction"].append({
                "level": "country", "geo": "india", "year": y, "quarter": q,
                "category": cat, "txn_count": 1e8 * (i + 1) * mult,
                "txn_amount": 1e11 * (i + 1) * mult})

    db = tmp_path / "test.duckdb"
    load_warehouse(rows, db_path=db)

    # Point config + service singleton at the temp warehouse.
    from src import config
    from src.serving import service
    monkeypatch.setattr(config, "DB_PATH", db)
    service.get_service.cache_clear()
    monkeypatch.setattr(service, "get_service", lambda: service.InsightService(db_path=db))

    from src.api.main import app
    return TestClient(app)


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["warehouse_ready"] is True


def test_meta_reports_states(client):
    r = client.get("/meta")
    assert r.status_code == 200 and r.json()["states"] == 2


def test_category_mix_sums_to_100(client):
    r = client.get("/kpis/category-mix")
    assert r.status_code == 200
    assert abs(sum(c["pct_value"] for c in r.json()) - 100.0) < 1e-6


def test_top_states_respects_n(client):
    r = client.get("/kpis/top-states?n=1")
    assert r.status_code == 200 and len(r.json()) == 1


def test_forecast_next_quarter_shape(client):
    r = client.get("/forecast/next-quarter")
    assert r.status_code == 200
    body = r.json()
    assert "quarter" in body and len(body["states"]) == 2
    assert {"forecast_champion", "forecast_ridge"} <= set(body["states"][0])


def test_unknown_state_404(client):
    assert client.get("/states/atlantis").status_code == 404


def test_segments_endpoint(client):
    r = client.get("/segments")
    assert r.status_code == 200 and r.json()["k"] >= 2
