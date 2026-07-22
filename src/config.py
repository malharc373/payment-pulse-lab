"""Central configuration for the UPI Reliability & Growth Intelligence pipeline.

All settings can be overridden via environment variables (see ``.env.example``),
which keeps the code reproducible across machines without editing source.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"          # cached raw JSON from the Pulse dataset
WAREHOUSE_DIR = DATA_DIR / "warehouse"
DB_PATH = Path(os.getenv("PULSE_DB_PATH", WAREHOUSE_DIR / "pulse.duckdb"))

# ---------------------------------------------------------------------------
# Pulse open dataset ("live" API)
# ---------------------------------------------------------------------------
# PhonePe publishes the Pulse aggregate data as static JSON served over HTTP.
# The canonical mirror is the raw content host for the public GitHub dataset.
PULSE_RAW_BASE = os.getenv(
    "PULSE_RAW_BASE",
    "https://raw.githubusercontent.com/PhonePe/pulse/master/data",
)
# GitHub trees API lets us *discover* which years/quarters/states exist without
# hard-coding them, so the pipeline stays correct as PhonePe adds new quarters.
PULSE_TREE_API = os.getenv(
    "PULSE_TREE_API",
    "https://api.github.com/repos/PhonePe/pulse/git/trees/master?recursive=1",
)

# ---------------------------------------------------------------------------
# Fetch scope. Defaults keep a first verification run quick while still being
# a genuine multi-quarter, multi-state slice. Widen via env for full history.
# ---------------------------------------------------------------------------
def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


MIN_YEAR = _int_env("PULSE_MIN_YEAR", 2020)
MAX_YEAR = _int_env("PULSE_MAX_YEAR", 2024)

# HTTP behaviour
HTTP_TIMEOUT = _int_env("PULSE_HTTP_TIMEOUT", 30)
HTTP_MAX_WORKERS = _int_env("PULSE_HTTP_WORKERS", 12)
HTTP_RETRIES = _int_env("PULSE_HTTP_RETRIES", 3)
USE_CACHE = os.getenv("PULSE_USE_CACHE", "1") not in ("0", "false", "False")

# The three dataset families and the two entities we ingest for Day-1 scope.
# (Insurance is available too and can be added the same way later.)
ENTITIES = ("transaction", "user")

# Light mode for memory-constrained hosts (e.g. Streamlit Cloud free tier):
# ingest only the small `aggregated` tables (skip the large `map`/`top` feeds)
# and disable the heavy district-grain forecast. State/category forecasts and the
# state choropleth all run off `aggregated`, so the dashboard stays fully useful.
LIGHT = os.getenv("PULSE_LIGHT", "0") not in ("0", "false", "False", "")
DEFAULT_DATASETS = ("aggregated",) if LIGHT else ("aggregated", "map", "top")
