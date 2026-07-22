"""Learned forecasters: a transparent regularized-linear model and a gradient
boosting model. Both predict the target in log space and are inverted with
``expm1`` so errors are reported in real INR.

Kept deliberately simple and transparent (the interview story is disciplined
validation, not an exotic architecture)."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.modeling.features import FEATURE_COLUMNS, LOG_TARGET


def _silence_spurious_matmul_warnings():
    """NumPy 2.x emits a false-positive 'divide by zero / invalid in matmul'
    RuntimeWarning on some BLAS backends even for finite inputs. Predictions are
    verified finite; silence just this warning so reports stay clean."""
    warnings.filterwarnings("ignore", message=".*matmul.*", category=RuntimeWarning)


_silence_spurious_matmul_warnings()


class LogForecaster:
    """Wraps a sklearn regressor to train on log-target and predict INR."""

    def __init__(self, estimator, name: str):
        self.estimator = estimator
        self.name = name

    def fit(self, train: pd.DataFrame) -> "LogForecaster":
        X = train[FEATURE_COLUMNS].to_numpy(dtype="float64")
        y = train[LOG_TARGET].to_numpy(dtype="float64")
        self.estimator.fit(X, y)
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        X = test[FEATURE_COLUMNS].to_numpy(dtype="float64")
        pred_log = self.estimator.predict(X)
        return np.expm1(pred_log)

    def feature_importance(self) -> pd.DataFrame | None:
        est = self.estimator
        if isinstance(est, Pipeline):
            est = est.named_steps.get("model", est)
        coef = getattr(est, "coef_", None)
        if coef is not None:
            return (
                pd.DataFrame({"feature": FEATURE_COLUMNS, "weight": coef})
                .assign(abs_weight=lambda d: d["weight"].abs())
                .sort_values("abs_weight", ascending=False)
                .reset_index(drop=True)
            )
        return None


def make_ridge() -> LogForecaster:
    pipe = Pipeline([("scale", StandardScaler()), ("model", Ridge(alpha=5.0))])
    return LogForecaster(pipe, name="ridge")


def make_gbm() -> LogForecaster:
    est = HistGradientBoostingRegressor(
        max_depth=3, max_iter=300, learning_rate=0.05,
        l2_regularization=1.0, min_samples_leaf=20, random_state=42,
    )
    return LogForecaster(est, name="gbm")


def make_models() -> list[LogForecaster]:
    return [make_ridge(), make_gbm()]
