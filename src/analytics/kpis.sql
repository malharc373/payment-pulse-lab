-- =====================================================================
-- kpis.sql : headline KPIs for the UPI Reliability & Growth dashboard.
-- Run against the DuckDB warehouse built by scripts/run_pipeline.py.
-- Each named block is an independent, copy-pasteable query.
-- =====================================================================

-- KPI 1 : National transaction volume & value by quarter -------------
--   The top-line growth story: are counts and value both rising?
SELECT year, quarter,
       SUM(txn_count)                    AS txn_count,
       ROUND(SUM(txn_amount)/1e7, 1)     AS txn_amount_cr   -- INR crore
FROM agg_transaction
WHERE level = 'country'
GROUP BY year, quarter
ORDER BY year, quarter;

-- KPI 2 : Average ticket size (value per transaction) over time ------
--   Rising ticket size vs rising count tells you *what kind* of growth.
SELECT year, quarter,
       ROUND(SUM(txn_amount) / NULLIF(SUM(txn_count), 0), 1) AS avg_ticket_inr
FROM agg_transaction
WHERE level = 'country'
GROUP BY year, quarter
ORDER BY year, quarter;

-- KPI 3 : Category mix in the latest available quarter ---------------
SELECT category,
       SUM(txn_count)                                      AS txn_count,
       ROUND(100.0 * SUM(txn_amount)
             / SUM(SUM(txn_amount)) OVER (), 1)            AS pct_of_value
FROM agg_transaction
WHERE level = 'country'
  AND (year * 10 + quarter) = (SELECT MAX(year * 10 + quarter)
                               FROM agg_transaction WHERE level = 'country')
GROUP BY category
ORDER BY pct_of_value DESC;

-- KPI 4 : Top 10 states by transaction value (latest quarter) --------
SELECT state,
       txn_count,
       ROUND(txn_amount/1e7, 1) AS txn_amount_cr
FROM state_txn_quarter
WHERE period_key = (SELECT MAX(period_key) FROM state_txn_quarter)
ORDER BY txn_amount DESC
LIMIT 10;

-- KPI 5 : Adoption intensity - transactions per registered user ------
--   A proxy for engagement, joining the transaction and user panels.
SELECT t.state,
       t.year, t.quarter,
       ROUND(t.txn_count::DOUBLE / NULLIF(u.registered_users, 0), 1)
           AS txns_per_registered_user
FROM state_txn_quarter t
JOIN state_user_quarter u USING (state, period_key)
WHERE t.period_key = (SELECT MAX(period_key) FROM state_txn_quarter)
ORDER BY txns_per_registered_user DESC
LIMIT 15;
