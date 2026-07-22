"""Forecast error metrics. WAPE is the headline: scale-free and robust to the
huge spread in state sizes (unlike MAPE, which explodes on small denominators)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _arr(y):
    return np.asarray(y, dtype="float64")


def mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(_arr(y_true) - _arr(y_pred))))


def rmse(y_true, y_pred) -> float:
    return float(np.sqrt(np.mean((_arr(y_true) - _arr(y_pred)) ** 2)))


def wape(y_true, y_pred) -> float:
    """Weighted Absolute Percentage Error = sum|e| / sum|y|."""
    yt = _arr(y_true)
    denom = np.sum(np.abs(yt))
    if denom == 0:
        return float("nan")
    return float(np.sum(np.abs(yt - _arr(y_pred))) / denom)


def smape(y_true, y_pred) -> float:
    """Symmetric MAPE in [0, 2]; avoids MAPE's small-denominator blow-ups."""
    yt, yp = _arr(y_true), _arr(y_pred)
    denom = np.abs(yt) + np.abs(yp)
    mask = denom != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(2 * np.abs(yt - yp)[mask] / denom[mask]))


def bias(y_true, y_pred) -> float:
    """Mean signed error as a fraction of mean actual (+ = over-forecast)."""
    yt = _arr(y_true)
    m = np.mean(yt)
    return float(np.mean(_arr(y_pred) - yt) / m) if m else float("nan")


def summary(y_true, y_pred) -> dict[str, float]:
    return {
        "WAPE": wape(y_true, y_pred),
        "sMAPE": smape(y_true, y_pred),
        "MAE": mae(y_true, y_pred),
        "RMSE": rmse(y_true, y_pred),
        "bias": bias(y_true, y_pred),
    }


def error_by_group(df: pd.DataFrame, group: str, y="y_true", yhat="y_pred") -> pd.DataFrame:
    """Per-group WAPE/MAE table, sorted worst-WAPE first."""
    rows = []
    for key, g in df.groupby(group):
        rows.append({group: key, "n": len(g),
                     "WAPE": wape(g[y], g[yhat]), "MAE": mae(g[y], g[yhat])})
    return pd.DataFrame(rows).sort_values("WAPE", ascending=False).reset_index(drop=True)
