"""Walk-forward (expanding-window) backtesting.

For each holdout quarter *t*, models are trained **only** on quarters strictly
before *t*, then asked to predict *t*. This mimics standing at the end of quarter
*t-1* and forecasting the next one — the only honest way to estimate real
forecasting error on a time series, and the reason we never use a random split.

    train: [.............< t ]  predict: [ t ]      <- fold for t
    train: [.............< t+1]  predict: [ t+1 ]    <- next fold (expanding)
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from src.modeling.baseline import BASELINES
from src.modeling.forecast import LogForecaster, make_models

TARGET = "txn_amount"


def default_test_periods(df: pd.DataFrame, n_holdout: int = 8) -> list[int]:
    """The last ``n_holdout`` quarters (by ordinal) become successive folds."""
    ords = sorted(df["period_ord"].unique())
    return ords[-n_holdout:]


def walk_forward(
    df: pd.DataFrame,
    test_periods: list[int] | None = None,
    models_factory: Callable[[], list[LogForecaster]] = make_models,
    min_train: int = 100,
) -> pd.DataFrame:
    """Run the backtest, returning long-form predictions for every model+baseline.

    Columns: state, period_key, period_ord, y_true, model, y_pred.
    """
    if test_periods is None:
        test_periods = default_test_periods(df)

    records: list[pd.DataFrame] = []
    for t in test_periods:
        train = df[df["period_ord"] < t]
        test = df[df["period_ord"] == t]
        if len(train) < min_train or test.empty:
            continue

        base_cols = {
            "state": test["state"].values,
            "period_key": test["period_key"].values,
            "period_ord": t,
            "y_true": test[TARGET].values,
        }

        # Naive baselines (no fitting; strictly-lagged columns).
        for b in BASELINES:
            rec = pd.DataFrame({**base_cols, "model": b.name, "y_pred": b.predict(test)})
            records.append(rec)

        # Learned models: fresh fit on the expanding training window each fold.
        for model in models_factory():
            model.fit(train)
            rec = pd.DataFrame({**base_cols, "model": model.name, "y_pred": model.predict(test)})
            records.append(rec)

    if not records:
        raise RuntimeError("No backtest folds ran; check min_train / test_periods.")
    out = pd.concat(records, ignore_index=True)
    # Guard against tiny negative predictions from expm1 rounding.
    out["y_pred"] = out["y_pred"].clip(lower=0.0)
    return out
