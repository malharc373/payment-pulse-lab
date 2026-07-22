"""FastAPI service exposing UPI growth intelligence over the DuckDB warehouse.

Endpoints are thin wrappers over :class:`InsightService`; all logic lives there so
the API and the dashboard stay consistent. Run:

    uvicorn src.api.main:app --reload
    # docs at http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from src.serving.service import get_service, warehouse_exists

app = FastAPI(
    title="UPI Reliability & Growth Intelligence API",
    version="1.0.0",
    description=(
        "Insights on public, aggregated PhonePe Pulse data: KPIs, growth, "
        "forecasts, anomalies, and regional segments. Outputs are areas for "
        "investigation, not claims about individuals."
    ),
)


def svc():
    if not warehouse_exists():
        raise HTTPException(
            status_code=503,
            detail="Warehouse not built. Run `make pipeline-full` first.",
        )
    return get_service()


@app.get("/health", tags=["meta"])
def health():
    ready = warehouse_exists()
    return {"status": "ok" if ready else "no_warehouse", "warehouse_ready": ready}


@app.get("/meta", tags=["meta"])
def meta():
    return svc().meta()


@app.get("/kpis/national-trend", tags=["analytics"])
def national_trend():
    return svc().national_trend()


@app.get("/quarters", tags=["analytics"])
def quarters():
    return svc().available_quarters()


@app.get("/kpis/category-mix", tags=["analytics"])
def category_mix(period_key: int | None = Query(None, description="e.g. 20234; default latest")):
    return svc().category_mix(period_key)


@app.get("/kpis/top-states", tags=["analytics"])
def top_states(n: int = Query(10, ge=1, le=36), period_key: int | None = None):
    return svc().top_states(n, period_key)


@app.get("/growth/leaders", tags=["growth"])
def growth_leaders(n: int = Query(15, ge=1, le=36)):
    return svc().growth_leaders(n)


@app.get("/growth/expansion-signals", tags=["growth"])
def expansion_signals():
    return svc().expansion_signals()


@app.get("/forecast/next-quarter", tags=["forecast"])
def forecast_next_quarter():
    return svc().forecast_next_quarter()


@app.get("/forecast/categories", tags=["forecast"])
def forecast_categories(top: int = Query(25, ge=1, le=200)):
    return svc().forecast_categories(top)


@app.get("/forecast/districts", tags=["forecast"])
def forecast_districts(top: int = Query(30, ge=1, le=500), state: str | None = None):
    return svc().forecast_districts(top, state=state)


@app.get("/map/states", tags=["analytics"])
def map_states(period_key: int | None = Query(None, description="e.g. 20234; default latest")):
    return svc().state_map_metrics(period_key)


@app.get("/anomalies", tags=["anomalies"])
def anomalies(top: int = Query(20, ge=1, le=200)):
    return svc().anomalies(top)


@app.get("/segments", tags=["segments"])
def segments():
    return svc().segments()


@app.get("/states", tags=["analytics"])
def states():
    return svc().states()


@app.get("/states/{state}", tags=["analytics"])
def state_detail(state: str):
    service = svc()
    if state not in service.states():
        raise HTTPException(status_code=404, detail=f"Unknown state '{state}'.")
    return service.state_detail(state)
