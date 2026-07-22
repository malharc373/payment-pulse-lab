"""Discover which Pulse dataset files exist, straight from the source.

Rather than hard-coding the 36 state slugs and the list of quarters (which grows
every three months), we ask the dataset's file tree what is actually available
and parse the directory convention into structured records.

Directory convention (everything lives under ``data/``)::

    aggregated/<entity>/country/india/<year>/<q>.json                # national
    aggregated/<entity>/country/india/state/<slug>/<year>/<q>.json    # per-state
    map/<entity>/hover/country/india/<year>/<q>.json                 # -> states
    map/<entity>/hover/country/india/state/<slug>/<year>/<q>.json    # -> districts
    top/<entity>/country/india/<year>/<q>.json                       # -> states/pincodes
    top/<entity>/country/india/state/<slug>/<year>/<q>.json          # -> districts/pincodes
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from src import config

# Bundled fallback manifest of all data paths (used when the GitHub API is
# rate-limited/unreachable — e.g. on Streamlit Cloud's shared IPs).
MANIFEST_PATH = Path(__file__).resolve().parent / "pulse_manifest.json"

# Path shape: <dataset>/<entity>/.../country/india[/state/<slug>]/<year>/<q>.json
_LEAF_RE = re.compile(r"(?P<year>\d{4})/(?P<quarter>[1-4])\.json$")
_STATE_RE = re.compile(r"/state/(?P<slug>[^/]+)/\d{4}/[1-4]\.json$")


@dataclass(frozen=True)
class PulseFile:
    """A single addressable JSON leaf in the Pulse dataset."""

    dataset: str       # aggregated | map | top
    entity: str        # transaction | user | insurance
    level: str         # country | state
    geo: str           # "india" for country level, else the state slug
    year: int
    quarter: int
    rel_path: str      # path relative to the data base (e.g. aggregated/.../1.json)

    @property
    def url(self) -> str:
        return f"{config.PULSE_RAW_BASE}/{self.rel_path}"

    @property
    def cache_key(self) -> str:
        """Filesystem-safe name used to cache the raw JSON on disk."""
        return self.rel_path.replace("/", "__")


def _classify(rel_path: str) -> PulseFile | None:
    """Turn a ``data/...`` path into a :class:`PulseFile`, or ``None`` to skip."""
    leaf = _LEAF_RE.search(rel_path)
    if not leaf:
        return None

    parts = rel_path.split("/")
    dataset, entity = parts[0], parts[1]
    if dataset not in ("aggregated", "map", "top"):
        return None
    if entity not in config.ENTITIES:
        return None

    state = _STATE_RE.search(rel_path)
    if state:
        level, geo = "state", state.group("slug")
    else:
        level, geo = "country", "india"

    return PulseFile(
        dataset=dataset,
        entity=entity,
        level=level,
        geo=geo,
        year=int(leaf.group("year")),
        quarter=int(leaf.group("quarter")),
        rel_path=rel_path,
    )


def _tree_from_api() -> list[str]:
    """Fetch the full ``data/...`` path list from the GitHub trees API.

    An optional ``GITHUB_TOKEN`` raises the unauthenticated 60/hr limit to
    5000/hr — useful on shared hosts (e.g. Streamlit Cloud) whose IPs are often
    already rate-limited.
    """
    headers = {}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(config.PULSE_TREE_API, headers=headers, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if body.get("truncated"):
        raise RuntimeError("Pulse file tree was truncated by the API; narrow the scope.")
    return [n["path"] for n in body.get("tree", []) if n.get("type") == "blob"]


def _tree_from_manifest() -> list[str]:
    """Fallback path list from the bundled manifest (no network to api.github.com)."""
    return json.loads(MANIFEST_PATH.read_text())["paths"]


def all_paths() -> list[str]:
    """Full ``data/...`` path list, preferring the live API, falling back to the
    committed manifest when the API is unreachable or rate-limited."""
    try:
        return _tree_from_api()
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        if MANIFEST_PATH.exists():
            print(f"[discover] GitHub API unavailable ({exc}); using bundled manifest.")
            return _tree_from_manifest()
        raise


def discover_files(
    datasets: tuple[str, ...] = ("aggregated", "map", "top"),
    min_year: int | None = None,
    max_year: int | None = None,
) -> list[PulseFile]:
    """Enumerate available Pulse JSON leaves, filtered to the requested scope."""
    min_year = config.MIN_YEAR if min_year is None else min_year
    max_year = config.MAX_YEAR if max_year is None else max_year

    files: list[PulseFile] = []
    for path in all_paths():
        if not path.startswith("data/") or not path.endswith(".json"):
            continue
        rel = path[len("data/"):]
        if rel.split("/", 1)[0] not in datasets:
            continue
        pf = _classify(rel)
        if pf and min_year <= pf.year <= max_year:
            files.append(pf)

    files.sort(key=lambda f: (f.dataset, f.entity, f.level, f.geo, f.year, f.quarter))
    return files


if __name__ == "__main__":  # pragma: no cover - manual smoke check
    fs = discover_files()
    print(f"Discovered {len(fs)} files across scope {config.MIN_YEAR}-{config.MAX_YEAR}")
    from collections import Counter

    by_kind = Counter((f.dataset, f.entity, f.level) for f in fs)
    for k, n in sorted(by_kind.items()):
        print(f"  {k[0]:11s} {k[1]:11s} {k[2]:8s} {n:5d}")
