"""Insight service: the single source of truth behind the API and dashboard.

Wraps the DuckDB warehouse (fast analytical SQL, run live) and the Phase-2 models
(forecast / anomaly / segmentation, computed once and cached in memory). Both the
FastAPI app and the Streamlit dashboard import this — so they can never disagree.
"""
from __future__ import annotations

import functools
import math

import duckdb
import pandas as pd

from src import config
from src.modeling.anomaly_detection import detect
from src.modeling.features import build_features, build_forecast_frame
from src.modeling.forecast import make_ridge
from src.modeling.segmentation import segment_states

CHAMPION = "seasonal_yoy"   # winner of the walk-forward backtest (see model_card)


def warehouse_exists() -> bool:
    return config.DB_PATH.exists()


def period_label(pk: int) -> str:
    return f"{pk // 10}Q{pk % 10}"


def _jsonable(value):
    """Coerce NaN/inf (not valid JSON) to None; recurse through dicts/lists."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


class InsightService:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.DB_PATH

    # -- low level ----------------------------------------------------
    def _sql(self, query: str, params: list | None = None) -> pd.DataFrame:
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            return con.execute(query, params or []).df()
        finally:
            con.close()

    def meta(self) -> dict:
        df = self._sql(
            "SELECT MIN(year*10+quarter) lo, MAX(year*10+quarter) hi, "
            "COUNT(DISTINCT geo) states FROM agg_transaction WHERE level='state'"
        ).iloc[0]
        return {
            "warehouse": str(self.db_path),
            "first_quarter": period_label(int(df.lo)),
            "latest_quarter": period_label(int(df.hi)),
            "states": int(df.states),
        }

    # -- descriptive analytics (live SQL) -----------------------------
    def national_trend(self) -> list[dict]:
        df = self._sql(
            """
            SELECT year, quarter,
                   SUM(txn_count)  AS txn_count,
                   SUM(txn_amount) AS txn_amount
            FROM agg_transaction WHERE level='country'
            GROUP BY year, quarter ORDER BY year, quarter
            """
        )
        df["quarter_label"] = (df.year * 10 + df.quarter).map(period_label)
        df["avg_ticket"] = df.txn_amount / df.txn_count
        return df.to_dict("records")

    def category_mix(self) -> list[dict]:
        return self._sql(
            """
            SELECT category,
                   SUM(txn_count)  AS txn_count,
                   SUM(txn_amount) AS txn_amount,
                   100.0 * SUM(txn_amount) / SUM(SUM(txn_amount)) OVER () AS pct_value
            FROM agg_transaction
            WHERE level='country'
              AND (year*10+quarter) = (SELECT MAX(year*10+quarter)
                                       FROM agg_transaction WHERE level='country')
            GROUP BY category ORDER BY pct_value DESC
            """
        ).to_dict("records")

    def top_states(self, n: int = 10) -> list[dict]:
        return self._sql(
            """
            SELECT state, txn_count, txn_amount
            FROM state_txn_quarter
            WHERE period_key = (SELECT MAX(period_key) FROM state_txn_quarter)
            ORDER BY txn_amount DESC LIMIT ?
            """,
            [n],
        ).to_dict("records")

    def growth_leaders(self, n: int = 15) -> list[dict]:
        return self._sql(
            """
            WITH qoq AS (
                SELECT state,
                       100.0*(txn_amount - LAG(txn_amount) OVER w)
                            / NULLIF(LAG(txn_amount) OVER w,0) AS g
                FROM state_txn_quarter
                WINDOW w AS (PARTITION BY state ORDER BY period_key)
            )
            SELECT state, ROUND(MEDIAN(g),1) AS median_qoq_pct,
                   ROUND(MIN(g),1) AS worst_qoq_pct, COUNT(g) AS quarters
            FROM qoq WHERE g IS NOT NULL
            GROUP BY state HAVING COUNT(g) >= 4
            ORDER BY median_qoq_pct DESC LIMIT ?
            """,
            [n],
        ).to_dict("records")

    def expansion_signals(self) -> list[dict]:
        """High YoY value growth but below-median engagement -> headroom."""
        return self._sql(
            """
            WITH latest AS (SELECT MAX(period_key) pk FROM state_txn_quarter),
                 eng AS (
                    SELECT t.state,
                           t.txn_count::DOUBLE/NULLIF(u.registered_users,0) AS tpu
                    FROM state_txn_quarter t JOIN state_user_quarter u USING (state, period_key)
                    WHERE t.period_key=(SELECT pk FROM latest)),
                 yoy AS (
                    SELECT state,
                           100.0*(txn_amount - LAG(txn_amount,4) OVER w)
                                /NULLIF(LAG(txn_amount,4) OVER w,0) AS yoy
                    FROM state_txn_quarter
                    WINDOW w AS (PARTITION BY state ORDER BY period_key)
                    QUALIFY period_key=(SELECT pk FROM latest))
            SELECT e.state, ROUND(y.yoy,1) AS yoy_value_pct, ROUND(e.tpu,1) AS txns_per_user
            FROM eng e JOIN yoy y USING (state)
            WHERE y.yoy > (SELECT MEDIAN(yoy) FROM yoy)
              AND e.tpu < (SELECT MEDIAN(tpu) FROM eng)
            ORDER BY y.yoy DESC
            """
        ).to_dict("records")

    def state_history(self, state: str) -> list[dict]:
        df = self._sql(
            """
            SELECT year, quarter, txn_count, txn_amount
            FROM state_txn_quarter WHERE state = ? ORDER BY period_key
            """,
            [state],
        )
        df["quarter_label"] = (df.year * 10 + df.quarter).map(period_label)
        return df.to_dict("records")

    def states(self) -> list[str]:
        return sorted(self._sql("SELECT DISTINCT state FROM state_txn_quarter").state)

    # -- model-backed outputs (cached) --------------------------------
    @functools.cached_property
    def _forecast_df(self) -> pd.DataFrame:
        train = build_features(db_path=self.db_path)
        fut = build_forecast_frame(db_path=self.db_path)
        ridge_pred = make_ridge().fit(train).predict(fut)
        out = fut[["state", "year", "quarter", "period_key"]].copy()
        out["forecast_champion"] = fut["seasonal_yoy"].to_numpy()
        out["forecast_ridge"] = ridge_pred
        out["last_actual"] = fut["naive_last"].to_numpy()
        out["growth_vs_last_pct"] = 100 * (out["forecast_champion"] / out["last_actual"] - 1)
        return out

    def forecast_next_quarter(self) -> dict:
        df = self._forecast_df.sort_values("forecast_champion", ascending=False)
        return _jsonable({
            "quarter": period_label(int(df.period_key.iloc[0])),
            "champion_model": CHAMPION,
            "states": df.drop(columns=["year", "quarter", "period_key"]).to_dict("records"),
        })

    @functools.cached_property
    def _anomaly_df(self) -> pd.DataFrame:
        return detect(build_features(db_path=self.db_path))

    def anomalies(self, top: int = 20) -> list[dict]:
        cols = ["state", "year", "quarter", "txn_amount", "qoq_amt",
                "user_growth", "value_user_gap", "avg_ticket", "anomaly_score"]
        return _jsonable(self._anomaly_df.head(top)[cols].to_dict("records"))

    @functools.cached_property
    def _segments(self):
        labelled, profile, meta = segment_states(build_features(db_path=self.db_path))
        return labelled, profile, meta

    def segments(self) -> dict:
        labelled, profile, meta = self._segments
        clusters = []
        for cl, g in labelled.groupby("cluster"):
            row = profile[profile.cluster == cl].iloc[0].to_dict()
            row["states"] = sorted(g.state.tolist())
            clusters.append(row)
        return _jsonable(
            {"k": meta["k"], "silhouette": meta["silhouette"], "clusters": clusters}
        )


@functools.lru_cache(maxsize=1)
def get_service() -> InsightService:
    """Process-wide singleton so caches are shared across requests."""
    return InsightService()
