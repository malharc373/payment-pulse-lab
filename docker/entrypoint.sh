#!/usr/bin/env bash
# Build the warehouse on first boot if it's missing, then run the given command.
# Lets a single container (Render / Fly / Cloud Run) be self-sufficient, while
# docker-compose's dedicated `pipeline` service still populates the shared volume
# first (in which case this check finds the DB and skips straight to the server).
set -euo pipefail

DB="${PULSE_DB_PATH:-/app/data/warehouse/pulse.duckdb}"
if [ ! -f "$DB" ]; then
  echo "[entrypoint] Warehouse missing at $DB — running ingestion pipeline..."
  python -m scripts.run_pipeline \
    --min-year "${PULSE_MIN_YEAR:-2020}" --max-year "${PULSE_MAX_YEAR:-2024}"
else
  echo "[entrypoint] Warehouse present at $DB — skipping build."
fi

exec "$@"
