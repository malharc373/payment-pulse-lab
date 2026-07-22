"""Cluster states into behavioural archetypes and describe each segment.

Usage:
    python -m scripts.run_segmentation           # auto-select k by silhouette
    python -m scripts.run_segmentation --k 4
"""
from __future__ import annotations

import argparse

import pandas as pd

from src import config
from src.modeling.segmentation import PROFILE_FEATURES, segment_states


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=None, help="clusters (default: auto)")
    args = ap.parse_args(argv)

    labelled, cluster_profile, meta = segment_states(k=args.k)
    print(f"Segmented {len(labelled)} states into k={meta['k']} clusters "
          f"(silhouette={meta['silhouette']:.3f})")
    if meta["silhouette_scores"]:
        sc = ", ".join(f"k={k}:{v:.3f}" for k, v in meta["silhouette_scores"].items())
        print(f"  silhouette by k: {sc}")

    prof = cluster_profile.copy()
    prof["yoy_growth"] = (100 * prof["yoy_growth"]).round(1)
    prof["user_growth"] = (100 * prof["user_growth"]).round(1)
    prof["txns_per_user"] = prof["txns_per_user"].round(1)
    prof["avg_ticket"] = prof["avg_ticket"].round(0)
    for c in ("share_merchant", "share_peer-to-peer", "share_recharge"):
        prof[c] = (100 * prof[c]).round(1)
    with pd.option_context("display.width", 150, "display.max_columns", None):
        print("\n=== Cluster profiles (means; growth/shares in %) ===")
        print(prof.to_string(index=False))

    print("\n=== States by cluster ===")
    for cl, g in labelled.groupby("cluster"):
        members = ", ".join(sorted(g["state"]))
        print(f"  Cluster {cl} ({len(g)}): {members}")

    out = config.PROJECT_ROOT / "reports" / "state_segments.csv"
    out.parent.mkdir(exist_ok=True)
    labelled.to_csv(out, index=False)
    print(f"\nSaved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
