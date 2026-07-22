"""Tests for feature engineering — above all, that there is NO temporal leakage."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.modeling import features as F


def _synthetic_panel(n_states=2, n_quarters=12, seed=0) -> pd.DataFrame:
    """A clean balanced panel with a known increasing series per state."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_states):
        amt = 1_000_000.0 * (s + 1)
        users = 100_000.0 * (s + 1)
        for i in range(n_quarters):
            year = 2018 + i // 4
            quarter = i % 4 + 1
            amt *= 1.1 + rng.normal(0, 0.02)
            users *= 1.05
            rows.append({
                "state": f"s{s}", "year": year, "quarter": quarter,
                "period_key": year * 10 + quarter,
                "txn_count": amt / 1500, "txn_amount": amt,
                "registered_users": users, "app_opens": users * 10,
                "share_merchant": 0.2, "share_peer-to-peer": 0.75,
                "share_recharge": 0.03, "share_financial": 0.01, "share_others": 0.01,
                "period_ord": year * 4 + (quarter - 1),
            })
    return pd.DataFrame(rows)


def test_lag_features_use_only_past_values():
    panel = _synthetic_panel()
    feat = F.build_features(panel.copy())
    # For each row, lag1_log_amt must equal log1p of the PREVIOUS quarter's amount.
    src = panel.sort_values(["state", "period_ord"]).set_index(["state", "period_ord"])
    for _, r in feat.iterrows():
        prev = src.loc[(r["state"], r["period_ord"] - 1), "txn_amount"]
        assert np.isclose(r["lag1_log_amt"], np.log1p(prev)), (r["state"], r["period_ord"])


def test_target_never_leaks_into_features():
    """Perturbing a quarter's OWN target must not change that row's features."""
    panel = _synthetic_panel()
    base = F.build_features(panel.copy())

    tampered = panel.copy()
    # Blow up one specific state-quarter's current target only.
    mask = (tampered.state == "s0") & (tampered.period_key == 20193)
    tampered.loc[mask, "txn_amount"] *= 1000
    after = F.build_features(tampered)

    row_b = base[(base.state == "s0") & (base.period_key == 20193)].iloc[0]
    row_a = after[(after.state == "s0") & (after.period_key == 20193)].iloc[0]
    # Features for THAT row are built from earlier quarters -> unchanged.
    for c in F.FEATURE_COLUMNS:
        assert np.isclose(row_b[c], row_a[c]), f"feature {c} leaked the current target"


def test_reindex_exposes_gaps():
    panel = _synthetic_panel(n_states=1, n_quarters=8)
    # Remove a middle quarter to create a gap.
    panel = panel[panel.period_key != 20193].copy()
    grid = F._reindex_full_grid(panel)
    # The missing quarter should reappear as a NaN-target row (so shift aligns).
    gap = grid[(grid.period_key == 20193)]
    assert len(gap) == 1 and np.isnan(gap.iloc[0]["txn_amount"])


def test_no_nan_or_inf_in_output_features():
    feat = F.build_features(_synthetic_panel())
    X = feat[F.FEATURE_COLUMNS].to_numpy("float64")
    assert np.isfinite(X).all()
