# UPI Reliability & Growth Intelligence

An end-to-end analytics platform on **PhonePe Pulse** public, aggregated, anonymized
UPI data. It ingests the open dataset over HTTP, builds a validated DuckDB warehouse,
and answers the questions a payments growth team actually asks: *where is adoption
accelerating, which categories are outpacing their region, and which movements are
anomalous enough to investigate?*

> Built on PhonePe's open data (CDLA-Permissive-2.0). All figures are aggregated and
> anonymized; insights are framed as **areas for investigation / growth opportunities**,
> never claims about individual users, merchants, or fraud.

## What's built

| Layer | Module | Status |
|---|---|---|
| **Ingestion** | `src/ingestion/` — dynamic file discovery, cached concurrent fetch, per-shape parsers | Phase 1 |
| **Warehouse** | `src/transforms/load_duckdb.py` — typed DuckDB tables + helper views | Phase 1 |
| **Data quality** | `src/transforms/quality_checks.py` — 7 checks (grain, nulls, panel completeness, reconciliation) | Phase 1 |
| **SQL analytics** | `src/analytics/*.sql` — KPIs, QoQ/YoY growth, concentration (HHI), robust anomaly flags | Phase 1 |
| **Forecasting** | `src/modeling/` + `src/evaluation/` — time-valid features, naive baselines, ridge & GBM, **walk-forward backtest** | Phase 2 |
| **Anomaly (ML)** | `src/modeling/anomaly_detection.py` — Isolation Forest over joint behaviour signals | Phase 2 |
| **Segmentation** | `src/modeling/segmentation.py` — K-Means state archetypes (silhouette-selected k) | Phase 2 |
| **API** | `src/api/` + `src/serving/` — FastAPI over an `InsightService` (15 endpoints) | Phase 3 |
| **Dashboard** | `dashboard/app.py` — Streamlit + Altair + Plotly, tabbed, CVD-validated palette | Phase 3 |
| **Deploy / CI** | Dockerfile + compose + Render/Fly configs; GitHub Actions (lint, tests, build) | Phase 3 |
| **Multi-grain forecasting** | `src/modeling/panels.py` — same leakage-free code forecasts state, **category & district** | Phase 4 |
| **Prediction intervals** | `src/modeling/intervals.py` — calibrated 10–90% bands from backtest residuals | Phase 4 |
| **Choropleth + drill-down** | India state map (Plotly) + per-state explore tab | Phase 4 |
| **Scheduled ingestion** | `.github/workflows/refresh-data.yml` — weekly re-ingest + validate | Phase 4 |
| **Shareable snapshot** | `scripts/build_artifact.py` — self-contained static HTML dashboard | Phase 4 |
| **Tests** | `tests/` — 49 unit tests incl. **temporal-leakage, panel, interval & API tests** | Done |

## Quickstart

```bash
make setup                 # venv + dependencies
make pipeline-full         # discover -> fetch -> load -> validate (2018-2024)
make kpis                  # headline KPI queries
make growth                # growth analysis
make anomaly-sql           # SQL anomaly flags (robust z-score / IQR)
make backtest              # walk-forward forecasting: baselines vs models
make anomaly               # Isolation Forest anomaly detection
make segment               # cluster states into archetypes
make api                   # FastAPI at http://localhost:8000/docs
make dashboard             # Streamlit at http://localhost:8501
make test                  # unit tests (incl. leakage tests)
```

Or the whole stack in Docker (builds the warehouse, then serves API + dashboard):

```bash
docker compose up --build   # API :8000/docs  ·  dashboard :8501
```

Or directly:

```bash
python -m scripts.run_pipeline --min-year 2018 --max-year 2024
python -m scripts.run_backtest --holdout 8
uvicorn src.api.main:app --reload
```

## How ingestion works

PhonePe serves Pulse as static JSON under a fixed directory convention. Rather than
hard-coding state slugs and quarters, the pipeline:

1. **Discovers** every available file from the dataset's file tree (GitHub trees API),
   parsing the directory convention into typed `PulseFile` records
   (`src/ingestion/discover.py`).
2. **Fetches** only the files that contribute rows, concurrently, caching raw JSON
   under `data/raw/` so re-runs are instant (`fetch_pulse_data.py`).
3. **Parses** each of five JSON shapes into tidy rows (`parsers.py`) — including the
   two subtly different map shapes (`hoverDataList` array vs `hoverData` object).
4. **Loads** typed tables and helper views into DuckDB (`transforms/load_duckdb.py`).
5. **Validates** with data-quality checks; the run exits non-zero on any FAIL so it
   is CI-ready.

```
discover ──► fetch (cached, concurrent) ──► parse ──► DuckDB warehouse ──► quality checks
```

## Warehouse tables

`agg_transaction`, `agg_user`, `map_transaction`, `map_user`, `top_transaction`,
plus helper views `state_txn_quarter` / `state_user_quarter`.
See [`docs/data_dictionary.md`](docs/data_dictionary.md) for full column definitions.

## Example insights (2022–2023 slice)

- **Category mix**: Peer-to-peer ≈ 76% of value, Merchant ≈ 20% — but merchant
  *count* exceeds P2P count, i.e. many small merchant payments vs fewer large P2P.
- **Sustained growth leaders** (median QoQ value growth): Andaman & Nicobar, Uttar
  Pradesh, Bihar, Jharkhand — smaller bases compounding fast.
- **Expansion signal**: states with high YoY value growth *and* below-median
  transactions-per-user (e.g. Ladakh, Mizoram, Uttar Pradesh) — candidate headroom.
- **Concentration (HHI)**: North-eastern states are the most category-concentrated;
  metros are the most diversified.
- **Anomalies**: robust z-scores flag the Q4→Q1 seasonal dip; district-level scan
  surfaces outsized single-quarter jumps worth a data-quality/growth look.

## Forecasting (Phase 2)

Predicts **next-quarter transaction value per state** with strict, leakage-free
methodology — the point of the project is disciplined validation, not an exotic model.

- **Time-valid features** — lagged levels/growth, engagement ratios, category mix,
  seasonality; every feature for quarter *t* uses only *t-1* and earlier
  (`groupby(state).shift`), verified by leakage unit tests.
- **Honest baselines** — random walk, seasonal naive, and seasonal×YoY.
- **Walk-forward validation** — expanding window over the last 8 quarters; models
  retrain each fold on strictly-earlier data. No random splits.

**Results (8-quarter holdout, 2023 Q1 – 2024 Q4):**

| Model | WAPE | sMAPE |
|---|---|---|
| **seasonal_yoy** (baseline) | **6.76%** | 9.5% |
| ridge | 7.08% | 10.6% |
| naive_last | 8.79% | 11.7% |
| gbm | 14.22% | 12.9% |
| seasonal_naive | 29.21% | 39.3% |

The disciplined **baseline wins**, with a regularized linear model within a point;
gradient boosting overfits this short, strongly-trending panel. Reporting that
honestly — and explaining *why* — is the intended takeaway. See
[`docs/model_card.md`](docs/model_card.md). Companion models: an **Isolation Forest**
anomaly detector (joint behaviour signals) and **K-Means** state segmentation.

## Product layer (Phase 3)

A **FastAPI** service and a **Streamlit** dashboard both sit on one `InsightService`
(`src/serving/`) — the single source of truth, so API and UI can never disagree.
See [`docs/architecture.md`](docs/architecture.md) for the full flow.

**API endpoints** (`http://localhost:8000/docs`):

| Endpoint | Returns |
|---|---|
| `GET /health`, `/meta` | readiness; warehouse coverage |
| `GET /kpis/national-trend`, `/category-mix`, `/top-states` | headline KPIs |
| `GET /growth/leaders`, `/growth/expansion-signals` | growth prioritization |
| `GET /forecast/next-quarter` | per-state next-quarter forecast (champion + ridge) |
| `GET /anomalies` | Isolation Forest flags |
| `GET /segments` | K-Means state archetypes |
| `GET /states`, `/states/{state}` | list; per-state history |

The **dashboard** renders KPI tiles, the national trend, category mix, top states,
next-quarter forecasts, growth/expansion tables, anomalies, and segment archetypes —
charts use a colorblind-safe categorical palette (validated with the dataviz skill).

Both are containerized: `docker compose up --build` runs the pipeline into a shared
volume, then serves the API (:8000) and dashboard (:8501).

## Continuous integration

`.github/workflows/ci.yml` runs on every push / PR:

1. **ruff** lint (real-bug subset + unused imports),
2. the **full test suite** — fully offline (synthetic fixtures + in-memory DuckDB),
   so no Pulse data is fetched in CI,
3. a **Docker image build** to catch packaging breakage.

The ingestion pipeline's data-quality checks also exit non-zero on any FAIL, so the
warehouse itself is gate-able in a scheduled job.

## Design choices

- **DuckDB first** — analytical SQL with zero infra; the whole warehouse is one file.
- **Dynamic discovery** — no hard-coded geography or quarters; new quarters ingest
  automatically.
- **Idempotent loads** — tables are rebuilt each run, so re-running never duplicates.
- **Robust statistics** — median/MAD and IQR for anomaly flags, not mean/std, so a
  single outlier quarter doesn't distort the baseline.

## Project layout

```
src/
  ingestion/   discover.py  fetch_pulse_data.py  parsers.py  schema.py
  transforms/  load_duckdb.py  quality_checks.py
  analytics/   kpis.sql  growth_analysis.sql  anomaly_queries.sql
  modeling/    features.py  baseline.py  forecast.py  anomaly_detection.py  segmentation.py
  evaluation/  metrics.py  backtest.py
  serving/     service.py            # InsightService — shared by API & dashboard
  api/         main.py               # FastAPI app
  config.py
dashboard/     app.py                # Streamlit + Altair
scripts/       run_pipeline.py  run_sql.py  run_backtest.py  run_anomaly.py  run_segmentation.py
tests/         test_parsers.py  test_quality_checks.py  test_features.py
               test_metrics.py  test_backtest.py  test_api.py
docs/          data_dictionary.md  model_card.md  architecture.md
.github/workflows/ci.yml             # lint + tests + docker build
Dockerfile  docker-compose.yml
reports/       backtest_predictions.csv  anomalies.csv  state_segments.csv  (generated)
```

## Deployment

The image self-builds its warehouse on first boot (`docker/entrypoint.sh`), so a
single container runs anywhere. See [`docs/DEPLOY.md`](docs/DEPLOY.md) for Docker
Compose, Render (`render.yaml`), Streamlit Community Cloud (`PULSE_AUTO_BUILD=1`),
and Fly.io / Cloud Run. A shareable, self-contained snapshot dashboard builds via
`make artifact`.

## Roadmap / possible extensions

- Quantile-regression intervals per grain (current bands are empirical residuals).
- District-level choropleth and category drill-downs in the map tab.
- Persist the warehouse to object storage so deploys skip the cold-start build.
