"""Smoke tests for the FastAPI layer, backed by a synthetic warehouse.

We build a small complete DuckDB (all five tables), point the service at it, and
exercise the routes with FastAPI's TestClient — no network, no real data.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests import synth


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = synth.build(tmp_path / "test.duckdb")

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
    assert client.get("/meta").json()["states"] == 2


def test_category_mix_sums_to_100(client):
    body = client.get("/kpis/category-mix").json()
    assert abs(sum(c["pct_value"] for c in body) - 100.0) < 1e-6


def test_top_states_respects_n(client):
    assert len(client.get("/kpis/top-states?n=1").json()) == 1


def test_forecast_next_quarter_has_intervals(client):
    body = client.get("/forecast/next-quarter").json()
    assert "quarter" in body and len(body["states"]) == 2
    row = body["states"][0]
    assert {"forecast_champion", "forecast_ridge", "forecast_lo", "forecast_hi"} <= set(row)
    assert row["forecast_lo"] <= row["forecast_champion"] <= row["forecast_hi"]


def test_forecast_categories(client):
    body = client.get("/forecast/categories?top=10").json()
    assert body["rows"] and {"state", "category"} <= set(body["rows"][0])


def test_forecast_districts(client):
    body = client.get("/forecast/districts?top=10").json()
    assert body["rows"] and {"state", "district"} <= set(body["rows"][0])


def test_map_states(client):
    body = client.get("/map/states").json()
    assert len(body) == 2 and "yoy_pct" in body[0]


def test_state_detail_drilldown(client):
    body = client.get("/states/karnataka").json()
    assert body["state"] == "karnataka"
    assert body["forecast"] is not None and "cluster" in body
    assert isinstance(body["history"], list) and len(body["history"]) > 0


def test_unknown_state_404(client):
    assert client.get("/states/atlantis").status_code == 404


def test_segments_endpoint(client):
    assert client.get("/segments").json()["k"] >= 2
