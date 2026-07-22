"""PULSE_LIGHT path: with no map/top data, district-grain code degrades cleanly
while state/category forecasts and the choropleth still work."""
from __future__ import annotations

import pytest

from src.serving.service import InsightService
from tests import synth


@pytest.fixture()
def light_service(tmp_path):
    db = synth.build(tmp_path / "light.duckdb", with_map=False)
    return InsightService(db_path=db)


def test_meta_reports_no_districts(light_service):
    m = light_service.meta()
    assert m["districts_available"] is False
    assert m["states"] == 2


def test_state_and_category_forecasts_still_work(light_service):
    assert light_service.forecast_next_quarter()["states"]
    assert light_service.forecast_categories(5)["rows"]


def test_district_forecast_empty_not_crash(light_service):
    out = light_service.forecast_districts(5)
    assert out["rows"] == []


def test_choropleth_metrics_available(light_service):
    assert len(light_service.state_map_metrics()) == 2
