"""Tests for prediction-interval construction from log-residuals."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.modeling import intervals


def _frame(actual, forecast):
    return pd.DataFrame({"txn_amount": actual, "seasonal_yoy": forecast})


def test_quantiles_zero_when_forecast_perfect():
    df = _frame([100.0] * 20, [100.0] * 20)
    lo, hi = intervals.residual_log_quantiles(df)
    assert abs(lo) < 1e-9 and abs(hi) < 1e-9


def test_add_intervals_brackets_point_forecast():
    lo, hi = intervals.add_intervals([100.0, 200.0], q_low=-0.2, q_high=0.3)
    f = np.array([100.0, 200.0])
    assert np.allclose(lo, [100 * np.exp(-0.2), 200 * np.exp(-0.2)])
    assert np.allclose(hi, [100 * np.exp(0.3), 200 * np.exp(0.3)])
    assert (lo < f).all() and (hi > f).all()


def test_coverage_is_calibrated():
    # Forecast that is off by lognormal noise -> ~80% inside the 10-90 interval.
    rng = np.random.default_rng(0)
    forecast = np.full(2000, 1_000_000.0)
    actual = forecast * np.exp(rng.normal(0, 0.3, size=2000))
    cov = intervals.coverage(_frame(actual, forecast), low=0.1, high=0.9)
    assert 0.75 <= cov <= 0.85


def test_too_few_points_returns_zero_width():
    df = _frame([100.0, 200.0], [90.0, 210.0])
    assert intervals.residual_log_quantiles(df) == (0.0, 0.0)
