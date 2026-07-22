"""Export a compact JSON snapshot of the key insights for the static dashboard.

Produces ``reports/snapshot.json`` — everything the shareable single-page
Artifact needs, baked in so the page is fully self-contained (no backend).
"""
from __future__ import annotations

import json

from src import config
from src.serving.service import get_service


def cr(x: float) -> float:
    return round(x / 1e7, 1)


def main() -> int:
    s = get_service()
    meta = s.meta()
    trend = s.national_trend()
    mix = s.category_mix()
    tops = s.top_states(10)
    fc = s.forecast_next_quarter()
    seg = s.segments()
    mp = s.state_map_metrics()

    snapshot = {
        "meta": meta,
        "trend": [{"q": t["quarter_label"], "value_cr": cr(t["txn_amount"]),
                   "count_bn": round(t["txn_count"] / 1e9, 2),
                   "ticket": round(t["avg_ticket"], 0)} for t in trend],
        "category_mix": [{"category": m["category"], "pct": round(m["pct_value"], 1)} for m in mix],
        "top_states": [{"state": t["state"], "value_cr": cr(t["txn_amount"])} for t in tops],
        "forecast": {
            "quarter": fc["quarter"], "model": fc["champion_model"],
            "rows": [{"state": r["state"], "champ_cr": cr(r["forecast_champion"]),
                      "lo_cr": cr(r["forecast_lo"]), "hi_cr": cr(r["forecast_hi"]),
                      "growth": round(r["growth_vs_last_pct"], 1)}
                     for r in fc["states"][:12]],
        },
        "segments": {"k": seg["k"], "silhouette": round(seg["silhouette"], 2),
                     "clusters": [{"cluster": int(c["cluster"]), "n": int(c["n_states"]),
                                   "yoy": round(100 * c["yoy_growth"], 0),
                                   "tpu": round(c["txns_per_user"], 0),
                                   "ticket": round(c["avg_ticket"], 0),
                                   "states": c["states"]} for c in seg["clusters"]]},
        "map": [{"state": m["state"], "value_cr": cr(m["txn_amount"]), "yoy": m["yoy_pct"]} for m in mp],
    }

    out = config.PROJECT_ROOT / "reports" / "snapshot.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2))
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
