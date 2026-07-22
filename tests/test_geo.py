"""Tests for Pulse-slug -> GeoJSON name matching."""
from __future__ import annotations

from src.serving import geo


def test_common_states_match():
    for slug, expected in [
        ("andhra-pradesh", "Andhra Pradesh"),
        ("karnataka", "Karnataka"),
        ("tamil-nadu", "Tamil Nadu"),
        ("jammu-&-kashmir", "Jammu & Kashmir"),
    ]:
        assert geo.slug_to_stnm(slug) == expected


def test_andaman_special_case():
    # Pulse says 'islands'; the GeoJSON says 'Andaman & Nicobar'.
    assert geo.slug_to_stnm("andaman-&-nicobar-islands") == "Andaman & Nicobar"


def test_all_36_geojson_states_covered_by_normalization():
    # Every GeoJSON state should normalize uniquely (no collisions).
    features = geo.load_geojson()["features"]
    norms = [geo.normalize(f["properties"]["ST_NM"]) for f in features]
    assert len(set(norms)) == len(norms) == 36


def test_unknown_slug_returns_none():
    assert geo.slug_to_stnm("atlantis") is None
