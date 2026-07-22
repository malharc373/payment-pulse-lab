"""Unit tests for the JSON parsers, using fixtures shaped like the real feed."""
from __future__ import annotations

from src.ingestion import parsers
from src.ingestion.discover import PulseFile


def _pf(dataset="aggregated", entity="transaction", level="state", geo="karnataka"):
    return PulseFile(
        dataset=dataset, entity=entity, level=level, geo=geo,
        year=2023, quarter=1,
        rel_path=f"{dataset}/{entity}/country/india/2023/1.json",
    )


def test_agg_transaction_sums_total_metric():
    body = {
        "data": {
            "transactionData": [
                {"name": "Merchant payments",
                 "paymentInstruments": [{"type": "TOTAL", "count": 10, "amount": 1.5e3}]},
                {"name": "Peer-to-peer payments",
                 "paymentInstruments": [{"type": "TOTAL", "count": 5, "amount": 2.0e3}]},
            ]
        }
    }
    table, rows = parsers.parse(_pf(), body)
    assert table == "agg_transaction"
    assert len(rows) == 2
    m = {r["category"]: r for r in rows}
    assert m["Merchant payments"]["txn_count"] == 10
    assert m["Merchant payments"]["txn_amount"] == 1500.0
    assert rows[0]["geo"] == "karnataka" and rows[0]["year"] == 2023


def test_agg_transaction_handles_null_instruments():
    body = {"data": {"transactionData": [{"name": "Others", "paymentInstruments": None}]}}
    _, rows = parsers.parse(_pf(), body)
    assert rows[0]["txn_count"] == 0 and rows[0]["txn_amount"] == 0.0


def test_agg_user_extracts_registered_and_appopens():
    body = {"data": {"aggregated": {"registeredUsers": 100, "appOpens": 900}, "usersByDevice": None}}
    table, rows = parsers.parse(_pf(entity="user"), body)
    assert table == "agg_user"
    assert rows[0]["registered_users"] == 100 and rows[0]["app_opens"] == 900


def test_agg_user_empty_when_no_aggregated():
    _, rows = parsers.parse(_pf(entity="user"), {"data": {"aggregated": {}}})
    assert rows == []


def test_map_transaction_uses_hoverdatalist_array():
    body = {"data": {"hoverDataList": [
        {"name": "bengaluru urban", "metric": [{"type": "TOTAL", "count": 7, "amount": 70.0}]},
    ]}}
    table, rows = parsers.parse(_pf(dataset="map"), body)
    assert table == "map_transaction"
    assert rows[0]["district"] == "bengaluru urban" and rows[0]["state"] == "karnataka"


def test_map_user_uses_hoverdata_object():
    body = {"data": {"hoverData": {"mysuru district": {"registeredUsers": 3, "appOpens": 40}}}}
    table, rows = parsers.parse(_pf(dataset="map", entity="user"), body)
    assert table == "map_user"
    assert rows[0]["district"] == "mysuru district" and rows[0]["registered_users"] == 3


def test_top_transaction_flattens_all_entity_types():
    body = {"data": {
        "states": [{"entityName": "maharashtra", "metric": {"type": "TOTAL", "count": 1, "amount": 1.0}}],
        "districts": [{"entityName": "pune", "metric": {"type": "TOTAL", "count": 2, "amount": 2.0}}],
        "pincodes": [{"entityName": "560001", "metric": {"type": "TOTAL", "count": 3, "amount": 3.0}}],
    }}
    table, rows = parsers.parse(_pf(dataset="top", level="country", geo="india"), body)
    assert table == "top_transaction"
    types = {r["entity_type"] for r in rows}
    assert types == {"state", "district", "pincode"}


def test_national_map_is_skipped():
    table, rows = parsers.parse(_pf(dataset="map", level="country", geo="india"), {"data": {}})
    assert table is None and rows == []


def test_is_ingested_routing():
    assert parsers.is_ingested(_pf())                                   # agg -> yes
    assert parsers.is_ingested(_pf(dataset="map", level="state"))       # state map -> yes
    assert not parsers.is_ingested(_pf(dataset="map", level="country")) # national map -> no
    assert not parsers.is_ingested(_pf(dataset="top", entity="user"))   # top/user -> no
