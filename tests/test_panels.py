"""Tests for the multi-grain panel builders."""
from __future__ import annotations

import pytest

from src.modeling import panels
from src.modeling.features import build_features, build_forecast_frame
from tests import synth


@pytest.fixture()
def db(tmp_path):
    return synth.build(tmp_path / "w.duckdb")


def _has_schema(df):
    for col in ["state", "year", "quarter", "period_key", "period_ord",
                "txn_count", "txn_amount", "registered_users", "app_opens"]:
        assert col in df.columns, col
    for c in panels.SHARE_COLS:
        assert c in df.columns


def test_category_panel_entities_and_schema(db):
    p = panels.category_panel(db)
    _has_schema(p)
    # 2 states x 3 categories = 6 entities.
    assert p["state"].nunique() == 6
    assert all(panels.SEP in e for e in p["state"].unique())


def test_district_panel_entities_and_join(db):
    p = panels.district_panel(db, min_quarters=8)
    _has_schema(p)
    assert p["state"].nunique() == 4          # 2 states x 2 districts
    # map_user join (suffix-normalized) populated user counts.
    assert p["registered_users"].notna().any()


def test_panels_feed_the_feature_pipeline(db):
    # The whole point: the same feature code runs on every grain without changes.
    for panel in (panels.category_panel(db), panels.district_panel(db)):
        feat = build_features(panel=panel)
        fut = build_forecast_frame(panel=panel)
        assert len(feat) > 0 and len(fut) == panel["state"].nunique()


def test_split_entity_roundtrip():
    assert panels.split_entity("karnataka | Merchant payments") == ("karnataka", "Merchant payments")
    assert panels.split_entity("karnataka") == ("karnataka", "")
