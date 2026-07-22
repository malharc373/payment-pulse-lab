"""Panel builders for multiple forecasting grains — state, category, district.

The feature machinery in :mod:`features` is entity-agnostic: it keys everything
off a single ``state`` column (the entity id) and a set of share columns. So we
reuse it for finer grains simply by producing panels with the **same schema**,
where ``state`` holds a composite entity id (e.g. ``"karnataka | Merchant
payments"``). Share columns that don't apply to a grain are set to 0 (the model
learns to ignore uninformative constant features).

This is why one leakage-tested code path forecasts every grain — no duplicated
feature logic, no new leakage surface.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from src import config
from src.modeling.features import _CAT_COL, load_state_panel

SHARE_COLS = list(_CAT_COL.values())
SEP = " | "   # entity-id separator, e.g. "karnataka | Merchant payments"


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Add period keys/ordinal and any missing share columns; sort chronologically."""
    df = df.copy()
    df["period_key"] = df["year"] * 10 + df["quarter"]
    df["period_ord"] = df["year"] * 4 + (df["quarter"] - 1)
    for c in SHARE_COLS:
        if c not in df.columns:
            df[c] = 0.0
    return df.sort_values(["state", "period_ord"]).reset_index(drop=True)


def state_panel(db_path=None) -> pd.DataFrame:
    """State grain — delegates to the original loader (has real category shares)."""
    return load_state_panel(db_path)


def category_panel(db_path=None) -> pd.DataFrame:
    """One row per (state, category, quarter). Entity = 'state | category'."""
    db_path = db_path or config.DB_PATH
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            """
            SELECT t.geo AS geo, t.category AS category, t.year, t.quarter,
                   t.txn_count, t.txn_amount,
                   u.registered_users, u.app_opens
            FROM agg_transaction t
            LEFT JOIN agg_user u
              ON t.geo = u.geo AND t.year = u.year AND t.quarter = u.quarter
             AND u.level = 'state'
            WHERE t.level = 'state'
            """
        ).df()
    finally:
        con.close()
    df["state"] = df["geo"] + SEP + df["category"]
    return _finalize(df)


def district_panel(db_path=None, min_quarters: int = 8) -> pd.DataFrame:
    """One row per (state, district, quarter). Entity = 'state | district'.

    District user counts come from the ``map_user`` feed, whose district names
    carry a ``' district'`` suffix that ``map_transaction`` lacks — so we join on
    a normalized name. Districts with too little history are dropped (they can't
    support lag features).
    """
    db_path = db_path or config.DB_PATH
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            """
            WITH u AS (
                SELECT state, REGEXP_REPLACE(LOWER(district), ' district$', '') AS district,
                       year, quarter, registered_users, app_opens
                FROM map_user
            )
            SELECT t.state AS geo, t.district AS district, t.year, t.quarter,
                   t.txn_count, t.txn_amount,
                   u.registered_users, u.app_opens
            FROM map_transaction t
            LEFT JOIN u
              ON t.state = u.state AND LOWER(t.district) = u.district
             AND t.year = u.year AND t.quarter = u.quarter
            """
        ).df()
    finally:
        con.close()
    df["state"] = df["geo"] + SEP + df["district"]
    df = _finalize(df)
    # Drop sparse districts that can't support the lag features.
    counts = df.groupby("state")["period_ord"].transform("count")
    return df[counts >= min_quarters].reset_index(drop=True)


def split_entity(entity: str) -> tuple[str, str]:
    """Split a composite entity id back into (parent, child); parent-only if no sep."""
    if SEP in entity:
        a, b = entity.split(SEP, 1)
        return a, b
    return entity, ""
