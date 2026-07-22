.PHONY: help setup pipeline pipeline-full kpis growth anomaly-sql \
        backtest anomaly segment models test clean

PY := ./.venv/bin/python
PIP := ./.venv/bin/pip

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

setup:  ## Create venv and install dependencies
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

pipeline:  ## Fetch + load + validate the default scope (2020-2024)
	$(PY) -m scripts.run_pipeline

pipeline-full:  ## Fetch + load the full available history
	$(PY) -m scripts.run_pipeline --min-year 2018 --max-year 2025

kpis:  ## Print headline KPI queries
	$(PY) -m scripts.run_sql src/analytics/kpis.sql

growth:  ## Print growth-analysis queries
	$(PY) -m scripts.run_sql src/analytics/growth_analysis.sql

anomaly-sql:  ## Print SQL anomaly queries (robust z-score / IQR)
	$(PY) -m scripts.run_sql src/analytics/anomaly_queries.sql

backtest:  ## Walk-forward forecasting backtest (baselines vs models)
	$(PY) -m scripts.run_backtest --holdout 8

anomaly:  ## Multivariate (Isolation Forest) anomaly detection
	$(PY) -m scripts.run_anomaly --top 20

segment:  ## Cluster states into behavioural archetypes
	$(PY) -m scripts.run_segmentation

models: backtest anomaly segment  ## Run all Phase-2 modeling steps

test:  ## Run the unit test suite
	$(PY) -m pytest -q

clean:  ## Remove the warehouse (keeps the raw cache)
	rm -f data/warehouse/*.duckdb data/warehouse/*.wal
