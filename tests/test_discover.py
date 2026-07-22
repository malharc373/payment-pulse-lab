"""Tests for file discovery, especially the offline manifest fallback.

These run without network: they force the GitHub API path to fail and assert the
bundled manifest yields a correctly-classified file list. This also guards the
manifest against going missing/empty in the repo.
"""
from __future__ import annotations

import json

import pytest
import requests

from src.ingestion import discover


def test_manifest_present_and_nonempty():
    data = json.loads(discover.MANIFEST_PATH.read_text())
    assert data["paths"] and all(p.startswith("data/") for p in data["paths"])


def test_fallback_used_when_api_fails(monkeypatch):
    def boom():
        raise requests.RequestException("simulated rate limit")

    monkeypatch.setattr(discover, "_tree_from_api", boom)
    files = discover.discover_files(min_year=2022, max_year=2023)
    assert files, "manifest fallback should yield files"
    # Classification still holds: valid grains, entities, years in range.
    assert all(2022 <= f.year <= 2023 for f in files)
    assert {f.dataset for f in files} <= {"aggregated", "map", "top"}
    assert any(f.level == "state" for f in files)


def test_year_filter_applies_to_manifest(monkeypatch):
    monkeypatch.setattr(discover, "_tree_from_api",
                        lambda: (_ for _ in ()).throw(requests.RequestException("x")))
    files = discover.discover_files(min_year=2021, max_year=2021)
    assert files and all(f.year == 2021 for f in files)


def test_token_header_used(monkeypatch):
    captured = {}

    class Resp:
        def raise_for_status(self): ...
        def json(self): return {"tree": [], "truncated": False}

    def fake_get(url, headers=None, timeout=None):
        captured["headers"] = headers or {}
        return Resp()

    monkeypatch.setenv("GITHUB_TOKEN", "secret123")
    monkeypatch.setattr(discover.requests, "get", fake_get)
    discover._tree_from_api()
    assert captured["headers"].get("Authorization") == "Bearer secret123"


@pytest.mark.parametrize("path,ok", [
    ("data/aggregated/transaction/country/india/2023/1.json", True),
    ("data/aggregated/insurance/country/india/2023/1.json", False),  # entity filtered
    ("README.md", False),
])
def test_classification_filters(path, ok):
    rel = path[len("data/"):] if path.startswith("data/") else path
    pf = discover._classify(rel) if path.startswith("data/") else None
    assert (pf is not None) == ok
