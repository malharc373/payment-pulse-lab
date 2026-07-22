# Data Dictionary — UPI Reliability & Growth Intelligence

Source: **PhonePe Pulse** open dataset (aggregated & anonymized), served as static
JSON over HTTP. Licence: CDLA-Permissive-2.0. All monetary amounts are in **INR
(rupees)**; the feed reports them as floating-point values.

> The data is aggregated and anonymized. Outputs are framed as *areas for further
> investigation* or *growth opportunities* — never claims about individual users,
> merchants, or fraud.

## Grain & periods

- **Period**: a calendar quarter, identified by `year` + `quarter` (1–4).
  A derived integer `period_key = year * 10 + quarter` (e.g. `20234`) gives a
  single sortable column for chronological ordering.
- **Geography**: `country` (india) and `state` levels for the aggregate feed;
  `district` level from the per-state map feed.

## Tables

### `agg_transaction` — transactions by category
One row per (level, geo, quarter, payment category).

| column | type | description |
|---|---|---|
| `level` | VARCHAR | `country` or `state` |
| `geo` | VARCHAR | `india` or the state slug (e.g. `karnataka`) |
| `year` | INTEGER | calendar year |
| `quarter` | INTEGER | 1–4 |
| `category` | VARCHAR | Merchant / Peer-to-peer / Recharge & bill / Financial Services / Others |
| `txn_count` | BIGINT | number of transactions |
| `txn_amount` | DOUBLE | total value (INR) |

### `agg_user` — registered users & engagement
One row per (level, geo, quarter).

| column | type | description |
|---|---|---|
| `level` | VARCHAR | `country` or `state` |
| `geo` | VARCHAR | `india` or state slug |
| `year`, `quarter` | INTEGER | period |
| `registered_users` | BIGINT | cumulative registered users |
| `app_opens` | BIGINT | app opens in the quarter |

### `map_transaction` — transactions by district
One row per (state, district, quarter). Sourced from per-state map files.

| column | type | description |
|---|---|---|
| `state` | VARCHAR | parent state slug |
| `district` | VARCHAR | district name as published |
| `year`, `quarter` | INTEGER | period |
| `txn_count` | BIGINT | number of transactions |
| `txn_amount` | DOUBLE | total value (INR) |

### `map_user` — users by district
Same grain as `map_transaction`, with `registered_users` and `app_opens`.

### `top_transaction` — ranked entities
Top states / districts / pincodes per parent geography.

| column | type | description |
|---|---|---|
| `parent_level` | VARCHAR | `country` or `state` |
| `parent_geo` | VARCHAR | `india` or state slug |
| `entity_type` | VARCHAR | `state`, `district`, or `pincode` |
| `entity_name` | VARCHAR | ranked entity name / pincode |
| `year`, `quarter` | INTEGER | period |
| `txn_count` | BIGINT | number of transactions |
| `txn_amount` | DOUBLE | total value (INR) |

## Helper views

| view | description |
|---|---|
| `state_txn_quarter` | state × quarter transaction totals (all categories summed) + `period_key` |
| `state_user_quarter` | state × quarter registered users & app opens + `period_key` |

## Known data notes

- `usersByDevice` (device brand breakdown) is `null` in recent quarters and is
  intentionally not ingested.
- National `map`/`top` rollups duplicate the aggregate state totals and are
  skipped during ingestion (see `parsers.is_ingested`).
- District names in `map_user` carry a `" district"` suffix that `map_transaction`
  does not — join on district with care, or normalize first.
