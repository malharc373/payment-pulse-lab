"""Prediction intervals from empirical backtest residuals.

A point forecast without uncertainty invites false confidence. We quantify it
honestly: the champion baseline (``seasonal_yoy``) is already a strictly-lagged
column on the feature frame, so its historical log-residuals
``r = log(actual) - log(forecast)`` are a leakage-free error sample. The chosen
quantiles of ``r`` become multiplicative bounds on any new forecast:

    lo = f * exp(q_low)      hi = f * exp(q_high)

Log space keeps the interval multiplicative (never negative) and roughly
symmetric across the wide range of entity sizes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.modeling.features import TARGET


def residual_log_quantiles(
    df: pd.DataFrame, forecast_col: str = "seasonal_yoy",
    low: float = 0.1, high: float = 0.9,
) -> tuple[float, float]:
    """Return (q_low, q_high) of the champion's historical log-residuals."""
    d = df[[TARGET, forecast_col]].replace([np.inf, -np.inf], np.nan).dropna()
    d = d[(d[TARGET] > 0) & (d[forecast_col] > 0)]
    if len(d) < 10:
        return 0.0, 0.0
    r = np.log(d[TARGET]) - np.log(d[forecast_col])
    return float(r.quantile(low)), float(r.quantile(high))


def add_intervals(
    forecast: pd.Series | np.ndarray, q_low: float, q_high: float
) -> tuple[np.ndarray, np.ndarray]:
    """Apply multiplicative log-residual bounds to a point forecast."""
    f = np.asarray(forecast, dtype="float64")
    return f * np.exp(q_low), f * np.exp(q_high)


def coverage(df: pd.DataFrame, forecast_col: str = "seasonal_yoy",
             low: float = 0.1, high: float = 0.9) -> float:
    """Empirical coverage of the interval on the same frame (sanity check).

    For a well-calibrated interval this should land near ``high - low``.
    """
    q_lo, q_hi = residual_log_quantiles(df, forecast_col, low, high)
    d = df[[TARGET, forecast_col]].replace([np.inf, -np.inf], np.nan).dropna()
    d = d[(d[TARGET] > 0) & (d[forecast_col] > 0)]
    lo, hi = add_intervals(d[forecast_col], q_lo, q_hi)
    inside = (d[TARGET].to_numpy() >= lo) & (d[TARGET].to_numpy() <= hi)
    return float(inside.mean())
