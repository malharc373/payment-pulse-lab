"""Multivariate anomaly detection over state-quarter behaviour.

Complements the univariate SQL flags (robust z-score / IQR) with an Isolation
Forest that considers several signals jointly — so a state-quarter can be flagged
for an *unusual combination* (e.g. value jumping while users are flat) that no
single metric would catch. Outputs are "areas for investigation", not judgements.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.modeling.features import build_features


def _behaviour_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Derive contemporaneous behaviour signals for each observed state-quarter.

    Unlike the forecasting features (which must be strictly lagged), anomaly
    detection describes the quarter itself, so we use current-quarter ratios.
    """
    d = df.sort_values(["state", "period_ord"]).copy()
    g = d.groupby("state", sort=False)
    d["qoq_amt"] = g["txn_amount"].pct_change()
    d["qoq_cnt"] = g["txn_count"].pct_change()
    d["avg_ticket"] = d["txn_amount"] / d["txn_count"].replace(0, np.nan)
    d["ticket_chg"] = d.groupby("state")["avg_ticket"].pct_change()
    d["user_growth"] = g["registered_users"].pct_change()
    d["txns_per_user"] = d["txn_count"] / d["registered_users"].replace(0, np.nan)
    # value-vs-user divergence: growth in value not matched by user growth
    d["value_user_gap"] = d["qoq_amt"] - d["user_growth"]

    cols = ["qoq_amt", "qoq_cnt", "avg_ticket", "ticket_chg",
            "user_growth", "txns_per_user", "value_user_gap"]
    d = d.replace([np.inf, -np.inf], np.nan).dropna(subset=cols)
    return d, cols


def detect(df: pd.DataFrame | None = None, contamination: float = 0.03,
           random_state: int = 42) -> pd.DataFrame:
    """Return state-quarters ranked by anomaly score (most anomalous first)."""
    if df is None:
        df = build_features()
    d, cols = _behaviour_frame(df)

    X = StandardScaler().fit_transform(d[cols].to_numpy("float64"))
    iso = IsolationForest(
        n_estimators=300, contamination=contamination, random_state=random_state
    )
    iso.fit(X)
    d = d.copy()
    d["anomaly_score"] = -iso.score_samples(X)   # higher = more anomalous
    d["is_anomaly"] = iso.predict(X) == -1

    keep = ["state", "year", "quarter", "txn_amount", "qoq_amt", "user_growth",
            "value_user_gap", "avg_ticket", "anomaly_score", "is_anomaly"]
    return d[keep].sort_values("anomaly_score", ascending=False).reset_index(drop=True)
