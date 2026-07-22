"""Tests that the walk-forward backtest never trains on the future."""
from __future__ import annotations

import numpy as np

from src.evaluation.backtest import walk_forward
from src.modeling import features as F
from tests.test_features import _synthetic_panel


class _SpyModel:
    """Records the maximum training period_ord it ever sees."""
    name = "spy"
    seen_max: list[int] = []

    def fit(self, train):
        _SpyModel.seen_max.append(int(train["period_ord"].max()))
        return self

    def predict(self, test):
        return np.zeros(len(test))


def _factory():
    return [_SpyModel()]


def test_training_window_is_strictly_past():
    df = F.build_features(_synthetic_panel(n_states=3, n_quarters=16))
    _SpyModel.seen_max = []
    test_periods = sorted(df["period_ord"].unique())[-3:]
    walk_forward(df, test_periods=test_periods, models_factory=_factory, min_train=1)
    # Every fold's max training period must be strictly before its test period.
    for t, max_train in zip(test_periods, _SpyModel.seen_max):
        assert max_train < t, f"leakage: trained up to {max_train} to predict {t}"


def test_output_shape_and_models_present():
    df = F.build_features(_synthetic_panel(n_states=3, n_quarters=16))
    test_periods = sorted(df["period_ord"].unique())[-2:]
    preds = walk_forward(df, test_periods=test_periods, min_train=1)
    assert {"naive_last", "seasonal_naive", "seasonal_yoy", "ridge", "gbm"} <= set(preds.model)
    assert (preds["y_pred"] >= 0).all()          # clipped, no negatives
    assert preds["y_true"].notna().all()
