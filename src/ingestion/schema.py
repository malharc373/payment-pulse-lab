"""Canonical row schemas produced by the parsers and loaded into DuckDB.

Keeping the target columns in one place documents the warehouse contract and
lets the loader create tables deterministically. Amounts are in INR (rupees);
the Pulse feed reports them as floats (often in scientific notation).
"""
from __future__ import annotations

# Long/tidy fact tables. Each row is one (geo, period, breakdown) observation.

AGG_TRANSACTION_COLUMNS = [
    "level",            # country | state
    "geo",              # india | <state-slug>
    "year",
    "quarter",
    "category",         # e.g. "Merchant payments", "Peer-to-peer payments"
    "txn_count",        # number of transactions
    "txn_amount",       # total value in INR
]

AGG_USER_COLUMNS = [
    "level",
    "geo",
    "year",
    "quarter",
    "registered_users",
    "app_opens",
]

# District-level metrics come from the per-state "map hover" files.
MAP_TRANSACTION_COLUMNS = [
    "state",            # parent state slug
    "district",         # district name as published
    "year",
    "quarter",
    "txn_count",
    "txn_amount",
]

MAP_USER_COLUMNS = [
    "state",
    "district",
    "year",
    "quarter",
    "registered_users",
    "app_opens",
]

# "top" files give ranked entities (states/districts/pincodes) per parent geo.
TOP_TRANSACTION_COLUMNS = [
    "parent_level",     # country | state
    "parent_geo",       # india | <state-slug>
    "entity_type",      # state | district | pincode
    "entity_name",
    "year",
    "quarter",
    "txn_count",
    "txn_amount",
]

TABLE_COLUMNS = {
    "agg_transaction": AGG_TRANSACTION_COLUMNS,
    "agg_user": AGG_USER_COLUMNS,
    "map_transaction": MAP_TRANSACTION_COLUMNS,
    "map_user": MAP_USER_COLUMNS,
    "top_transaction": TOP_TRANSACTION_COLUMNS,
}
