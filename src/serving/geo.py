"""Geo helpers: match Pulse state slugs to the India GeoJSON's ``ST_NM`` names.

Kept separate from the dashboard so the (fiddly) name normalization is unit-
tested rather than eyeballed. 35/36 states match on a plain normalization; the
one exception (Andaman & Nicobar) is handled by dropping the ``island(s)`` token.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

GEOJSON_PATH = Path(__file__).resolve().parents[2] / "dashboard" / "assets" / "india_states.geojson"
FEATURE_ID_KEY = "properties.ST_NM"


def normalize(name: str) -> str:
    """Lowercase, expand '&'->'and', drop island token & all non-letters."""
    s = name.lower().replace("&", "and")
    s = re.sub(r"island[s]?", "", s)
    return re.sub(r"[^a-z]", "", s)


@functools.lru_cache(maxsize=1)
def load_geojson() -> dict:
    return json.loads(GEOJSON_PATH.read_text())


@functools.lru_cache(maxsize=1)
def _norm_to_stnm() -> dict[str, str]:
    return {normalize(f["properties"]["ST_NM"]): f["properties"]["ST_NM"]
            for f in load_geojson()["features"]}


def slug_to_stnm(slug: str) -> str | None:
    """Map a Pulse state slug (e.g. 'andhra-pradesh') to the GeoJSON ST_NM."""
    return _norm_to_stnm().get(normalize(slug))
