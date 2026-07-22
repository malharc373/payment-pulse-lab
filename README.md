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
| **Ingestion** | `src/ingestion/` — dynamic file discovery, cached concurrent fetch, per-shape parsers | ✅ Phase 1 |
| **Warehouse** | `src/transforms/load_duckdb.py` — typed DuckDB tables + helper views | ✅ Phase 1 |
| **Data quality** | `src/transforms/quality_checks.py` — 7 checks (grain, nulls, panel completeness, reconciliation) | ✅ Phase 1 |
| **SQL analytics** | `src/analytics/*.sql` — KPIs, QoQ/YoY growth, concentration (HHI), robust anomaly flags | ✅ Phase 1 |
| **Forecasting** | `src/modeling/` + `src/evaluation/` — time-valid features, naive baselines, ridge & GBM, **walk-forward backtest** | ✅ Phase 2 |
| **Anomaly (ML)** | `src/modeling/anomaly_detection.py` — Isolation Forest over joint behaviour signals | ✅ Phase 2 |
| **Segmentation** | `src/modeling/segmentation.py` — K-Means state archetypes (silhouette-selected k) | ✅ Phase 2 |
| **Tests** | `tests/` — 26 unit tests incl. **temporal-leakage tests** | ✅ |
| API + dashboard | FastAPI + Streamlit, Docker | ⏳ Phase 3 |

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
make test                  # unit tests (incl. leakage tests)
```

Or directly:

```bash
python -m scripts.run_pipeline --min-year 2018 --max-year 2024
python -m scripts.run_backtest --holdout 8
python -m scripts.run_sql src/analytics/growth_analysis.sql --limit 10
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
  config.py
scripts/       run_pipeline.py  run_sql.py  run_backtest.py  run_anomaly.py  run_segmentation.py
tests/         test_parsers.py  test_quality_checks.py  test_features.py  test_metrics.py  test_backtest.py
docs/          data_dictionary.md  model_card.md
reports/       backtest_predictions.csv  anomalies.csv  state_segments.csv  (generated)
```

## Roadmap

- **Phase 3 — Product**: FastAPI endpoints (forecasts, anomalies, growth leaders) +
  Streamlit dashboard, Docker, architecture diagram.
