# Architecture

End-to-end flow from the public Pulse dataset to the API and dashboard.

```mermaid
flowchart LR
    subgraph Source["PhonePe Pulse (open data)"]
        RAW["Static JSON over HTTP<br/>aggregated · map · top"]
        TREE["GitHub trees API<br/>(file discovery)"]
    end

    subgraph Ingestion["Ingestion (src/ingestion)"]
        DISC["discover.py<br/>enumerate files"]
        FETCH["fetch_pulse_data.py<br/>cached · concurrent"]
        PARSE["parsers.py<br/>5 JSON shapes → rows"]
    end

    subgraph Warehouse["Warehouse (src/transforms)"]
        LOAD["load_duckdb.py<br/>typed tables + views"]
        QC["quality_checks.py<br/>7 checks (CI-gating)"]
        DB[("DuckDB<br/>pulse.duckdb")]
    end

    subgraph Analytics["Analytics & Models"]
        SQL["analytics/*.sql<br/>KPIs · growth · anomalies"]
        FEAT["modeling/features.py<br/>time-valid features"]
        FCST["forecast + baselines<br/>walk-forward backtest"]
        ANOM["Isolation Forest"]
        SEG["K-Means segments"]
    end

    subgraph Serving["Serving (src/serving + api)"]
        SVC["InsightService<br/>(single source of truth)"]
        API["FastAPI<br/>/forecast /anomalies ..."]
        DASH["Streamlit dashboard"]
    end

    TREE --> DISC --> FETCH --> PARSE --> LOAD --> DB
    LOAD --> QC
    DB --> SQL
    DB --> FEAT --> FCST
    FEAT --> ANOM
    FEAT --> SEG
    DB --> SVC
    FCST --> SVC
    ANOM --> SVC
    SEG --> SVC
    SVC --> API
    SVC --> DASH
    RAW -.serves.-> FETCH
```

## Key properties

- **Discovery-driven ingestion** — no hard-coded states/quarters; new quarters
  ingest automatically from the file tree.
- **Idempotent warehouse** — tables rebuilt each run; re-runs never duplicate.
- **Leakage-free modeling** — every forecasting feature is strictly lagged;
  validation is walk-forward, never a random split. Enforced by unit tests.
- **One source of truth** — API and dashboard both read `InsightService`, so
  they can never disagree.
- **CI-gated** — `quality_checks` exits non-zero on any FAIL; GitHub Actions runs
  lint + the offline test suite + a Docker image build on every push.

## Deployment

`docker compose up --build` runs a one-shot `pipeline` service to populate a
shared `pulse-data` volume, then starts `api` (:8000) and `dashboard` (:8501),
both depending on the pipeline completing successfully.
