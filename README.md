# UPI Reliability & Growth Intelligence

An end-to-end analytics platform on **PhonePe Pulse** public, aggregated, anonymized
UPI data. It ingests the open dataset over HTTP, builds a validated DuckDB warehouse,
and answers the questions a payments growth team actually asks: *where is adoption
accelerating, which categories are outpacing their region, and which movements are
anomalous enough to investigate?*

> Built on PhonePe's open data (CDLA-Permissive-2.0). All figures are aggregated and
> anonymized; insights are framed as **areas for investigation / growth opportunities**,
> never claims about individual users, merchants, or fraud.

## What's built (Phase 1 — data & SQL foundation)

| Layer | Module | Status |
|---|---|---|
| **Ingestion** | `src/ingestion/` — dynamic file discovery, cached concurrent fetch, per-shape parsers | ✅ |
| **Warehouse** | `src/transforms/load_duckdb.py` — typed DuckDB tables + helper views | ✅ |
| **Data quality** | `src/transforms/quality_checks.py` — 7 checks (grain, nulls, panel completeness, reconciliation) | ✅ |
| **SQL analytics** | `src/analytics/*.sql` — KPIs, QoQ/YoY growth, concentration (HHI), robust anomaly flags | ✅ |
| **Tests** | `tests/` — 14 unit tests (parsers, loader, checks) | ✅ |
| Modeling | forecasting (walk-forward), anomaly ML, segmentation | ⏳ Phase 2 |
| API + dashboard | FastAPI + Streamlit, Docker | ⏳ Phase 3 |

## Quickstart

```bash
make setup                 # venv + dependencies
make pipeline              # discover -> fetch -> load -> validate  (~45s for 2 yrs)
make kpis                  # headline KPI queries
make growth                # growth analysis
make anomaly               # anomaly detection
make test                  # unit tests
```

Or directly:

```bash
python -m scripts.run_pipeline --min-year 2022 --max-year 2023
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
  config.py
scripts/       run_pipeline.py  run_sql.py
tests/         test_parsers.py  test_quality_checks.py
docs/          data_dictionary.md
```

## Roadmap

- **Phase 2 — Modeling**: time-valid features, naïve seasonal baseline, walk-forward
  backtesting, one forecasting model (regularized GBM), ML anomaly detector, state
  segmentation. Report MAE/WAPE by state & category.
- **Phase 3 — Product**: FastAPI endpoints + Streamlit dashboard, Docker, model card.
