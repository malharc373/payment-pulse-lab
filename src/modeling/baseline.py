"""Naive, time-aware baselines. A forecast is only worth reporting if it beats
these — they are the honest bar for "did the model actually learn anything?".

Each baseline reads a precomputed column from the feature frame (all strictly
lagged, so there is no leakage) and returns predictions in the original INR scale.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class Baseline:
    name: str
    column: str

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return df[self.column].to_numpy(dtype="float64")


class NaiveLast(Baseline):
    """Next quarter = last quarter (random-walk)."""
    name = "naive_last"
    column = "naive_last"


class SeasonalNaive(Baseline):
    """Next quarter = same quarter one year ago (captures seasonality)."""
    name = "seasonal_naive"
    column = "seasonal_naive"


class SeasonalYoY(Baseline):
    """Seasonal naive scaled by the latest year-over-year growth ratio."""
    name = "seasonal_yoy"
    column = "seasonal_yoy"


BASELINES = [NaiveLast(), SeasonalNaive(), SeasonalYoY()]
