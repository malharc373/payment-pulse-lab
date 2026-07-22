"""Unsupervised segmentation of states by their digital-payment behaviour.

Each state is summarized by a behavioural profile (recent growth, category mix,
engagement, ticket size), standardized, and clustered with K-Means. K is chosen
by silhouette score over a small range. The output is a labelled table plus a
per-cluster profile that a growth team can read as regional archetypes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from src.modeling.features import build_features

PROFILE_FEATURES = [
    "yoy_growth",          # recent year-over-year value growth
    "txns_per_user",       # engagement
    "avg_ticket",          # value per transaction
    "user_growth",         # recent registered-user growth
    "share_merchant",      # category mix
    "share_peer-to-peer",
    "share_recharge",
]


def build_state_profiles(df: pd.DataFrame | None = None, recent_quarters: int = 4) -> pd.DataFrame:
    """One row per state summarizing its most recent behaviour."""
    if df is None:
        df = build_features()
    d = df.sort_values(["state", "period_ord"]).copy()
    g = d.groupby("state", sort=False)

    d["avg_ticket"] = d["txn_amount"] / d["txn_count"].replace(0, np.nan)
    d["txns_per_user"] = d["txn_count"] / d["registered_users"].replace(0, np.nan)
    d["yoy_growth"] = g["txn_amount"].pct_change(4)
    d["user_growth"] = g["registered_users"].pct_change(4)
    # category shares are already columns: share_merchant, share_peer-to-peer, ...

    recent = d.groupby("state").tail(recent_quarters)
    prof = recent.groupby("state").agg(
        yoy_growth=("yoy_growth", "mean"),
        txns_per_user=("txns_per_user", "mean"),
        avg_ticket=("avg_ticket", "mean"),
        user_growth=("user_growth", "mean"),
        **{"share_merchant": ("share_merchant", "mean"),
           "share_peer-to-peer": ("share_peer-to-peer", "mean"),
           "share_recharge": ("share_recharge", "mean")},
    ).replace([np.inf, -np.inf], np.nan).dropna()
    return prof


def choose_k(X: np.ndarray, k_range=range(2, 7), random_state: int = 42) -> tuple[int, dict[int, float]]:
    scores = {}
    for k in k_range:
        if k >= len(X):
            break
        labels = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit_predict(X)
        scores[k] = silhouette_score(X, labels)
    best_k = max(scores, key=scores.get)
    return best_k, scores


def segment_states(df: pd.DataFrame | None = None, k: int | None = None,
                   random_state: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Cluster states. Returns (labelled_profiles, cluster_profile, meta)."""
    prof = build_state_profiles(df)
    X = StandardScaler().fit_transform(prof[PROFILE_FEATURES].to_numpy("float64"))

    if k is None:
        k, scores = choose_k(X)
    else:
        scores = {}
    km = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit(X)
    prof = prof.copy()
    prof["cluster"] = km.labels_

    cluster_profile = (
        prof.groupby("cluster")[PROFILE_FEATURES].mean()
        .assign(n_states=prof.groupby("cluster").size())
        .reset_index()
    )
    meta = {"k": k, "silhouette_scores": scores,
            "silhouette": silhouette_score(X, km.labels_)}
    return prof.reset_index(), cluster_profile, meta
