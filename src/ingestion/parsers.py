"""Parse each Pulse JSON shape into flat, warehouse-ready row dicts.

Every parser takes the :class:`PulseFile` (for geo/period context) plus the
decoded JSON body, and returns ``(table_name, list_of_rows)``. Parsers are
deliberately defensive: the feed occasionally carries ``null`` sections or
empty arrays, and a single bad file must not abort a multi-thousand-file run.
"""
from __future__ import annotations

from typing import Any

from src.ingestion.discover import PulseFile


class ParseError(ValueError):
    """Raised when a file's structure does not match any known Pulse shape."""


def is_ingested(pf: PulseFile) -> bool:
    """Whether this file contributes rows, so we can skip fetching the rest.

    Mirrors the routing in :func:`parse`: national map/top rollups and top/user
    files are intentionally not loaded, so there's no point downloading them.
    """
    if pf.dataset == "aggregated":
        return True
    if pf.dataset == "map":
        return pf.level == "state"
    if pf.dataset == "top":
        return pf.entity == "transaction"
    return False


def _total_metric(metric_list: list[dict[str, Any]] | None) -> tuple[int, float]:
    """Sum the TOTAL metric entry (Pulse only ever ships a single TOTAL row)."""
    count, amount = 0, 0.0
    for m in metric_list or []:
        count += int(m.get("count") or 0)
        amount += float(m.get("amount") or 0.0)
    return count, amount


def parse_agg_transaction(pf: PulseFile, body: dict[str, Any]) -> list[dict[str, Any]]:
    data = (body or {}).get("data") or {}
    rows = []
    for cat in data.get("transactionData") or []:
        count, amount = _total_metric(cat.get("paymentInstruments"))
        rows.append(
            {
                "level": pf.level,
                "geo": pf.geo,
                "year": pf.year,
                "quarter": pf.quarter,
                "category": cat.get("name"),
                "txn_count": count,
                "txn_amount": amount,
            }
        )
    return rows


def parse_agg_user(pf: PulseFile, body: dict[str, Any]) -> list[dict[str, Any]]:
    data = (body or {}).get("data") or {}
    agg = data.get("aggregated") or {}
    if not agg:
        return []
    return [
        {
            "level": pf.level,
            "geo": pf.geo,
            "year": pf.year,
            "quarter": pf.quarter,
            "registered_users": int(agg.get("registeredUsers") or 0),
            "app_opens": int(agg.get("appOpens") or 0),
        }
    ]


def parse_map_transaction(pf: PulseFile, body: dict[str, Any]) -> list[dict[str, Any]]:
    """Only per-state map files yield districts; national maps duplicate the
    aggregated state totals and are skipped by the dispatcher."""
    data = (body or {}).get("data") or {}
    rows = []
    for entry in data.get("hoverDataList") or []:
        count, amount = _total_metric(entry.get("metric"))
        rows.append(
            {
                "state": pf.geo,
                "district": entry.get("name"),
                "year": pf.year,
                "quarter": pf.quarter,
                "txn_count": count,
                "txn_amount": amount,
            }
        )
    return rows


def parse_map_user(pf: PulseFile, body: dict[str, Any]) -> list[dict[str, Any]]:
    """map/user uses an object keyed by district name, unlike map/transaction."""
    data = (body or {}).get("data") or {}
    hover = data.get("hoverData") or {}
    rows = []
    for district, vals in hover.items():
        vals = vals or {}
        rows.append(
            {
                "state": pf.geo,
                "district": district,
                "year": pf.year,
                "quarter": pf.quarter,
                "registered_users": int(vals.get("registeredUsers") or 0),
                "app_opens": int(vals.get("appOpens") or 0),
            }
        )
    return rows


def parse_top_transaction(pf: PulseFile, body: dict[str, Any]) -> list[dict[str, Any]]:
    data = (body or {}).get("data") or {}
    rows = []
    for entity_type in ("states", "districts", "pincodes"):
        for entry in data.get(entity_type) or []:
            metric = entry.get("metric") or {}
            rows.append(
                {
                    "parent_level": pf.level,
                    "parent_geo": pf.geo,
                    "entity_type": entity_type[:-1],  # states -> state
                    "entity_name": entry.get("entityName"),
                    "year": pf.year,
                    "quarter": pf.quarter,
                    "txn_count": int(metric.get("count") or 0),
                    "txn_amount": float(metric.get("amount") or 0.0),
                }
            )
    return rows


def parse(pf: PulseFile, body: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    """Dispatch a file to the right parser, returning (table_name, rows).

    Returns ``(None, [])`` for files we intentionally ignore (e.g. national
    map/top rollups that would duplicate the aggregated tables).
    """
    ds, ent, lvl = pf.dataset, pf.entity, pf.level

    if ds == "aggregated" and ent == "transaction":
        return "agg_transaction", parse_agg_transaction(pf, body)
    if ds == "aggregated" and ent == "user":
        return "agg_user", parse_agg_user(pf, body)

    # Districts only exist inside per-state map files.
    if ds == "map" and lvl == "state" and ent == "transaction":
        return "map_transaction", parse_map_transaction(pf, body)
    if ds == "map" and lvl == "state" and ent == "user":
        return "map_user", parse_map_user(pf, body)
    if ds == "map":
        return None, []  # national map == aggregated state totals; skip

    if ds == "top" and ent == "transaction":
        return "top_transaction", parse_top_transaction(pf, body)
    if ds == "top":
        return None, []  # top/user ranks users; out of Day-1 scope

    raise ParseError(f"No parser for {ds}/{ent}/{lvl}: {pf.rel_path}")
