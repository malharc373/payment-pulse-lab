"""Walk-forward forecasting backtest: compare naive baselines vs learned models.

Usage:
    python -m scripts.run_backtest                 # 8-quarter holdout
    python -m scripts.run_backtest --holdout 6
Outputs a leaderboard, per-model error, worst/best states, and feature weights,
and writes the raw fold predictions to reports/backtest_predictions.csv.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src import config
from src.evaluation import metrics
from src.evaluation.backtest import default_test_periods, walk_forward
from src.modeling.features import build_features
from src.modeling.forecast import make_ridge


def _period_label(pk: int) -> str:
    return f"{pk // 10}Q{pk % 10}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", type=int, default=8, help="number of holdout quarters")
    args = ap.parse_args(argv)

    print("Building features...")
    df = build_features()
    periods = default_test_periods(df, n_holdout=args.holdout)
    lo, hi = df[df.period_ord == periods[0]].period_key.iloc[0], \
        df[df.period_ord == periods[-1]].period_key.iloc[0]
    print(f"Panel: {len(df)} state-quarters | holdout {_period_label(lo)}..{_period_label(hi)} "
          f"({len(periods)} folds, expanding window)")

    preds = walk_forward(df, test_periods=periods)

    # ---- Leaderboard (overall, across all folds) ----
    print("\n=== Forecast accuracy (lower WAPE is better) ===")
    rows = []
    for model, g in preds.groupby("model"):
        s = metrics.summary(g.y_true, g.y_pred)
        rows.append({"model": model, **s})
    board = pd.DataFrame(rows).sort_values("WAPE").reset_index(drop=True)
    board_fmt = board.assign(
        WAPE=lambda d: (100 * d.WAPE).round(2).astype(str) + "%",
        sMAPE=lambda d: (100 * d["sMAPE"]).round(2).astype(str) + "%",
        MAE=lambda d: (d.MAE / 1e7).round(1),           # INR crore
        RMSE=lambda d: (d.RMSE / 1e7).round(1),
        bias=lambda d: (100 * d.bias).round(1).astype(str) + "%",
    ).rename(columns={"MAE": "MAE_cr", "RMSE": "RMSE_cr"})
    print(board_fmt.to_string(index=False))

    best = board.iloc[0]["model"]
    naive = board[board.model == "naive_last"].iloc[0]["WAPE"]
    best_wape = board.iloc[0]["WAPE"]
    lift = 100 * (1 - best_wape / naive) if naive else float("nan")
    print(f"\nBest model: {best} — WAPE {100*best_wape:.2f}% "
          f"({lift:+.1f}% vs naive-last).")

    # ---- Error by fold (does accuracy hold across quarters?) ----
    print("\n=== WAPE by holdout quarter (best model vs seasonal naive) ===")
    fold_rows = []
    for pk, g in preds.groupby("period_key"):
        row = {"quarter": _period_label(pk)}
        for m in (best, "seasonal_naive"):
            gm = g[g.model == m]
            row[m] = round(100 * metrics.wape(gm.y_true, gm.y_pred), 2)
        fold_rows.append(row)
    print(pd.DataFrame(fold_rows).to_string(index=False))

    # ---- Where the best model wins / struggles (by state) ----
    bm = preds[preds.model == best].rename(columns={"y_true": "y_true", "y_pred": "y_pred"})
    by_state = metrics.error_by_group(bm, "state")
    print(f"\n=== {best}: hardest 8 states (highest WAPE) ===")
    print(by_state.head(8).assign(WAPE=lambda d: (100*d.WAPE).round(1)).to_string(index=False))
    print(f"\n=== {best}: easiest 5 states (lowest WAPE) ===")
    print(by_state.tail(5).assign(WAPE=lambda d: (100*d.WAPE).round(1)).to_string(index=False))

    # ---- Transparent drivers (ridge weights on a full-history fit) ----
    ridge = make_ridge().fit(df)
    fi = ridge.feature_importance()
    if fi is not None:
        print("\n=== Ridge feature weights (log-space, top 10 by |weight|) ===")
        print(fi.head(10).round(3).to_string(index=False))

    out = config.PROJECT_ROOT / "reports" / "backtest_predictions.csv"
    out.parent.mkdir(exist_ok=True)
    preds.to_csv(out, index=False)
    print(f"\nSaved fold predictions -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
