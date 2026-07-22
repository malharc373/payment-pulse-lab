"""Time-valid feature engineering for state-level quarterly forecasting.

The single most important property here is **no leakage**: every feature used to
predict quarter *t* is derived only from data available at *t-1* or earlier. We
enforce that structurally — all lag/rolling features are computed with pandas
``groupby(state).shift(k)`` on a chronologically-ordered, gap-reindexed panel, so
a feature row for period *t* can never see period *t*'s own target.

Target: total transaction **value** (INR) for a state in a quarter, modelled in
log space (``log1p``) because state sizes span several orders of magnitude.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from src import config

CATEGORIES = [
    "Merchant payments",
    "Peer-to-peer payments",
    "Recharge & bill payments",
    "Financial Services",
    "Others",
]
_CAT_COL = {c: "share_" + c.split()[0].lower() for c in CATEGORIES}

TARGET = "txn_amount"
LOG_TARGET = "y_log"


def load_state_panel(db_path=None) -> pd.DataFrame:
    """Load one row per (state, quarter) with totals, users, and category shares."""
    db_path = db_path or config.DB_PATH
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        base = con.execute(
            """
            SELECT t.state, t.year, t.quarter, t.period_key,
                   t.txn_count, t.txn_amount,
                   u.registered_users, u.app_opens
            FROM state_txn_quarter t
            LEFT JOIN state_user_quarter u USING (state, period_key)
            """
        ).df()
        cats = con.execute(
            """
            SELECT geo AS state, year, quarter, category, txn_amount
            FROM agg_transaction WHERE level = 'state'
            """
        ).df()
    finally:
        con.close()

    # Category value shares per state-quarter (pivot to wide).
    cats["period_key"] = cats["year"] * 10 + cats["quarter"]
    tot = cats.groupby(["state", "period_key"])["txn_amount"].transform("sum")
    cats["share"] = cats["txn_amount"] / tot.replace(0, np.nan)
    wide = (
        cats.pivot_table(index=["state", "period_key"], columns="category",
                         values="share", aggfunc="sum")
        .reindex(columns=CATEGORIES)
        .rename(columns=_CAT_COL)
        .reset_index()
    )
    panel = base.merge(wide, on=["state", "period_key"], how="left")

    # Even, gap-aware chronological ordinal (quarters, not the sparse period_key).
    panel["period_ord"] = panel["year"] * 4 + (panel["quarter"] - 1)
    return panel.sort_values(["state", "period_ord"]).reset_index(drop=True)


def _reindex_full_grid(panel: pd.DataFrame) -> pd.DataFrame:
    """Insert NaN rows for any missing (state, quarter) so shift() aligns to real
    calendar lags rather than silently skipping gaps."""
    states = panel["state"].unique()
    ords = range(int(panel["period_ord"].min()), int(panel["period_ord"].max()) + 1)
    grid = pd.MultiIndex.from_product([states, ords], names=["state", "period_ord"])
    out = (
        panel.set_index(["state", "period_ord"])
        .reindex(grid)
        .reset_index()
        .sort_values(["state", "period_ord"])
        .reset_index(drop=True)
    )
    # Recover year/quarter for synthetic rows from the ordinal.
    out["year"] = out["period_ord"] // 4
    out["quarter"] = out["period_ord"] % 4 + 1
    out["period_key"] = out["year"] * 10 + out["quarter"]
    return out


# Core lags that must exist for a row to be modellable at all.
_CORE_LAGS = ["lag1_log_amt", "lag4_log_amt", "roll4_log_amt", "qoq_amt_lag1"]


def _engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all strictly-lagged features + baseline columns on a gridded panel.

    Every derived column reads only ``shift(k>=1)`` values, so a row for quarter
    *t* never sees *t*'s own target — the guarantee our leakage tests enforce.
    """
    g = df.groupby("state", sort=False)
    df[LOG_TARGET] = np.log1p(df[TARGET])
    log_amt = np.log1p(df[TARGET])

    # --- Lagged level features (log space) ---
    for k in (1, 2, 4):
        df[f"lag{k}_log_amt"] = g[TARGET].shift(k).pipe(np.log1p)
        df[f"lag{k}_log_cnt"] = g["txn_count"].shift(k).pipe(np.log1p)
    df["roll4_log_amt"] = (
        log_amt.groupby(df["state"]).shift(1)
        .groupby(df["state"]).rolling(4, min_periods=2).mean()
        .reset_index(level=0, drop=True)
    )

    # --- Lagged growth features ---
    df["qoq_amt_lag1"] = g[TARGET].shift(1) / g[TARGET].shift(2) - 1
    df["yoy_amt_lag1"] = g[TARGET].shift(1) / g[TARGET].shift(5) - 1
    df["qoq_cnt_lag1"] = g["txn_count"].shift(1) / g["txn_count"].shift(2) - 1

    # --- Lagged user / engagement features ---
    df["lag1_log_users"] = g["registered_users"].shift(1).pipe(np.log1p)
    df["user_growth_lag1"] = g["registered_users"].shift(1) / g["registered_users"].shift(2) - 1
    df["txns_per_user_lag1"] = g["txn_count"].shift(1) / g["registered_users"].shift(1)
    df["appopens_per_user_lag1"] = g["app_opens"].shift(1) / g["registered_users"].shift(1)

    # --- Lagged category shares (mix at t-1) ---
    for col in _CAT_COL.values():
        df[f"{col}_lag1"] = g[col].shift(1)

    # --- Seasonality (target quarter is known ahead of time) ---
    df["q_sin"] = np.sin(2 * np.pi * df["quarter"] / 4)
    df["q_cos"] = np.cos(2 * np.pi * df["quarter"] / 4)

    # Baseline reference columns (used by naive forecasters & evaluation).
    df["naive_last"] = g[TARGET].shift(1)                 # last quarter
    df["seasonal_naive"] = g[TARGET].shift(4)             # same quarter last year
    df["seasonal_yoy"] = g[TARGET].shift(4) * (g[TARGET].shift(1) / g[TARGET].shift(5))
    return df


def _fill_sparse(df: pd.DataFrame) -> pd.DataFrame:
    """Fill remaining sparse ratio/growth features (after core-lag rows are kept).

    Applied only once the caller has dropped rows lacking the core lags, so this
    never resurrects garbage early-history rows — it just zero-fills the handful
    of higher-order ratios (e.g. yoy needing 5 quarters) in kept rows. Safe in
    log/ratio space and never uses future information.
    """
    df = df.copy()
    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return df


def build_features(panel: pd.DataFrame | None = None, db_path=None) -> pd.DataFrame:
    """Return the training frame: strictly-lagged features + a real target.

    Rows without a target or without the core lags are dropped.
    """
    if panel is None:
        panel = load_state_panel(db_path)
    df = _engineer(_reindex_full_grid(panel))
    df = df.dropna(subset=[TARGET] + _CORE_LAGS).reset_index(drop=True)
    return _fill_sparse(df)


def build_forecast_frame(panel: pd.DataFrame | None = None, db_path=None) -> pd.DataFrame:
    """Return one feature row per state for the **next, not-yet-observed** quarter.

    Appends a future quarter (target unknown) to the panel, engineers the same
    lagged features from known history, and returns those future rows. Their
    baseline columns (``seasonal_yoy`` etc.) are also populated, so both learned
    and naive next-quarter forecasts are available.
    """
    if panel is None:
        panel = load_state_panel(db_path)
    next_ord = int(panel["period_ord"].max()) + 1
    year, q = next_ord // 4, next_ord % 4 + 1
    future = pd.DataFrame({
        "state": panel["state"].unique(),
        "year": year, "quarter": q, "period_key": year * 10 + q,
        "period_ord": next_ord,
    })
    combined = pd.concat([panel, future], ignore_index=True)
    df = _engineer(_reindex_full_grid(combined))
    fut = df[(df["period_ord"] == next_ord) & df[_CORE_LAGS].notna().all(axis=1)]
    return _fill_sparse(fut.reset_index(drop=True))


FEATURE_COLUMNS = [
    "lag1_log_amt", "lag2_log_amt", "lag4_log_amt",
    "lag1_log_cnt", "lag2_log_cnt", "lag4_log_cnt",
    "roll4_log_amt",
    "qoq_amt_lag1", "yoy_amt_lag1", "qoq_cnt_lag1",
    "lag1_log_users", "user_growth_lag1",
    "txns_per_user_lag1", "appopens_per_user_lag1",
    "share_merchant_lag1", "share_peer-to-peer_lag1", "share_recharge_lag1",
    "share_financial_lag1", "share_others_lag1",
    "q_sin", "q_cos",
]
