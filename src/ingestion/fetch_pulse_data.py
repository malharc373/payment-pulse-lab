"""Concurrent, cached HTTP fetcher for the Pulse open dataset.

Raw JSON is cached under ``data/raw/`` keyed by its dataset path, so re-running
the pipeline is instant and polite to the origin. Network failures are retried
with simple backoff; a file that still fails is reported, not fatal.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Iterable

import requests

from src import config
from src.ingestion.discover import PulseFile


@dataclass
class FetchResult:
    pf: PulseFile
    body: dict[str, Any] | None
    from_cache: bool
    error: str | None = None


def _cache_path(pf: PulseFile):
    return config.RAW_DIR / f"{pf.cache_key}"


def _read_cache(pf: PulseFile) -> dict[str, Any] | None:
    p = _cache_path(pf)
    if config.USE_CACHE and p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return None  # corrupt cache -> refetch
    return None


def _write_cache(pf: PulseFile, body: dict[str, Any]) -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(pf).write_text(json.dumps(body))


def _fetch_one(pf: PulseFile, session: requests.Session) -> FetchResult:
    cached = _read_cache(pf)
    if cached is not None:
        return FetchResult(pf, cached, from_cache=True)

    last_err = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            resp = session.get(pf.url, timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 404:
                return FetchResult(pf, None, from_cache=False, error="404 not found")
            resp.raise_for_status()
            body = resp.json()
            _write_cache(pf, body)
            return FetchResult(pf, body, from_cache=False)
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_err = str(exc)
            time.sleep(0.5 * (attempt + 1))
    return FetchResult(pf, None, from_cache=False, error=last_err)


def fetch_all(
    files: Iterable[PulseFile],
    progress: Callable[[int, int], None] | None = None,
) -> list[FetchResult]:
    """Fetch every file concurrently, returning results in completion order."""
    files = list(files)
    results: list[FetchResult] = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "upi-growth-intelligence/0.1"})
        with ThreadPoolExecutor(max_workers=config.HTTP_MAX_WORKERS) as pool:
            futures = {pool.submit(_fetch_one, pf, session): pf for pf in files}
            for i, fut in enumerate(as_completed(futures), start=1):
                results.append(fut.result())
                if progress:
                    progress(i, len(files))
    return results
