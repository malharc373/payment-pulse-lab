"""Run the multivariate (Isolation Forest) anomaly detector over state-quarters.

Usage:
    python -m scripts.run_anomaly --top 20 --contamination 0.03
"""
from __future__ import annotations

import argparse

import pandas as pd

from src import config
from src.modeling.anomaly_detection import detect


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--contamination", type=float, default=0.03)
    args = ap.parse_args(argv)

    res = detect(contamination=args.contamination)
    n_flagged = int(res["is_anomaly"].sum())
    print(f"Scored {len(res)} state-quarters | {n_flagged} flagged "
          f"(contamination={args.contamination})")

    show = res.head(args.top).assign(
        txn_cr=lambda d: (d.txn_amount / 1e7).round(0),
        qoq=lambda d: (100 * d.qoq_amt).round(1),
        user_g=lambda d: (100 * d.user_growth).round(1),
        val_user_gap=lambda d: (100 * d.value_user_gap).round(1),
        ticket=lambda d: d.avg_ticket.round(0),
        score=lambda d: d.anomaly_score.round(3),
    )[["state", "year", "quarter", "txn_cr", "qoq", "user_g",
       "val_user_gap", "ticket", "score", "is_anomaly"]]
    with pd.option_context("display.width", 140, "display.max_columns", None):
        print("\n=== Most anomalous state-quarters (areas for investigation) ===")
        print(show.to_string(index=False))

    out = config.PROJECT_ROOT / "reports" / "anomalies.csv"
    out.parent.mkdir(exist_ok=True)
    res.to_csv(out, index=False)
    print(f"\nSaved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
