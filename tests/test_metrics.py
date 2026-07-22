"""Tests for forecast error metrics on hand-computed values."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.evaluation import metrics


def test_mae_and_rmse():
    y = [100.0, 200.0, 300.0]
    p = [110.0, 180.0, 300.0]
    assert metrics.mae(y, p) == (10 + 20 + 0) / 3
    assert metrics.rmse(y, p) == np.sqrt((100 + 400 + 0) / 3)


def test_wape_is_sum_abs_error_over_sum_actual():
    y = [100.0, 200.0, 300.0]           # sum = 600
    p = [110.0, 180.0, 330.0]           # abs errors 10, 20, 30 = 60
    assert metrics.wape(y, p) == 60 / 600


def test_wape_handles_zero_actual():
    assert np.isnan(metrics.wape([0, 0], [1, 2]))


def test_bias_sign():
    # Consistent over-forecast -> positive bias.
    assert metrics.bias([100, 100], [110, 110]) > 0
    assert metrics.bias([100, 100], [90, 90]) < 0


def test_smape_bounded():
    val = metrics.smape([100, 200], [50, 400])
    assert 0 <= val <= 2


def test_error_by_group_sorts_worst_first():
    df = pd.DataFrame({
        "state": ["a", "a", "b", "b"],
        "y_true": [100, 100, 100, 100],
        "y_pred": [100, 100, 50, 50],   # b is worse
    })
    out = metrics.error_by_group(df, "state")
    assert list(out["state"]) == ["b", "a"]
    assert out.iloc[0]["WAPE"] == 0.5
