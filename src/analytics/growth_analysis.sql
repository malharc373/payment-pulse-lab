-- =====================================================================
-- growth_analysis.sql : quarter-over-quarter & year-over-year growth,
-- category outperformance, concentration, and expansion signals.
-- =====================================================================

-- G1 : Quarter-over-quarter growth per state (value & count) ----------
SELECT state, year, quarter,
       ROUND(txn_amount/1e7, 1)                                  AS txn_amount_cr,
       ROUND(100.0 * (txn_amount - LAG(txn_amount) OVER w)
             / NULLIF(LAG(txn_amount) OVER w, 0), 1)             AS qoq_value_pct,
       ROUND(100.0 * (txn_count - LAG(txn_count) OVER w)
             / NULLIF(LAG(txn_count) OVER w, 0), 1)              AS qoq_count_pct
FROM state_txn_quarter
WINDOW w AS (PARTITION BY state ORDER BY period_key)
ORDER BY state, period_key;

-- G2 : Sustained growth leaders --------------------------------------
--   Rank states by *median* QoQ value growth so one lucky spike doesn't win.
WITH qoq AS (
    SELECT state, period_key,
           100.0 * (txn_amount - LAG(txn_amount) OVER w)
                 / NULLIF(LAG(txn_amount) OVER w, 0) AS g
    FROM state_txn_quarter
    WINDOW w AS (PARTITION BY state ORDER BY period_key)
)
SELECT state,
       ROUND(MEDIAN(g), 1)                 AS median_qoq_pct,
       ROUND(MIN(g), 1)                    AS worst_qoq_pct,
       COUNT(g)                            AS quarters_measured
FROM qoq
WHERE g IS NOT NULL
GROUP BY state
HAVING COUNT(g) >= 3
ORDER BY median_qoq_pct DESC
LIMIT 15;

-- G3 : Year-over-year growth (same quarter last year) ----------------
--   Removes seasonality by comparing like quarters.
SELECT state, year, quarter,
       ROUND(100.0 * (txn_amount - LAG(txn_amount, 4) OVER w)
             / NULLIF(LAG(txn_amount, 4) OVER w, 0), 1) AS yoy_value_pct
FROM state_txn_quarter
WINDOW w AS (PARTITION BY state ORDER BY period_key)
QUALIFY yoy_value_pct IS NOT NULL
ORDER BY yoy_value_pct DESC
LIMIT 20;

-- G4 : Categories outpacing their region -----------------------------
--   Which category grows faster than the state's overall trend? These are
--   the mix-shifts a growth team would want to understand.
WITH cat AS (
    SELECT geo AS state, category, year, quarter,
           year * 10 + quarter AS period_key, txn_amount
    FROM agg_transaction WHERE level = 'state'
),
cat_g AS (
    SELECT state, category, period_key,
           100.0 * (txn_amount - LAG(txn_amount) OVER w)
                 / NULLIF(LAG(txn_amount) OVER w, 0) AS cat_growth
    FROM cat
    WINDOW w AS (PARTITION BY state, category ORDER BY period_key)
),
state_g AS (
    SELECT state, period_key,
           100.0 * (txn_amount - LAG(txn_amount) OVER w)
                 / NULLIF(LAG(txn_amount) OVER w, 0) AS state_growth
    FROM state_txn_quarter
    WINDOW w AS (PARTITION BY state ORDER BY period_key)
)
SELECT c.state, c.category, c.period_key,
       ROUND(c.cat_growth, 1)                       AS cat_qoq_pct,
       ROUND(s.state_growth, 1)                     AS state_qoq_pct,
       ROUND(c.cat_growth - s.state_growth, 1)      AS outperformance_pts
FROM cat_g c JOIN state_g s USING (state, period_key)
WHERE c.cat_growth IS NOT NULL
  AND c.period_key = (SELECT MAX(period_key) FROM state_txn_quarter)
ORDER BY outperformance_pts DESC
LIMIT 20;

-- G5 : Category concentration (Herfindahl-Hirschman Index) -----------
--   HHI near 1 = one category dominates; near 0.2 = diversified (5 cats).
SELECT geo AS state,
       ROUND(SUM(share * share), 3) AS hhi
FROM (
    SELECT geo, category,
           txn_amount / SUM(txn_amount) OVER (PARTITION BY geo) AS share
    FROM agg_transaction
    WHERE level = 'state'
      AND (year * 10 + quarter) = (SELECT MAX(period_key) FROM state_txn_quarter)
)
GROUP BY geo
ORDER BY hhi DESC
LIMIT 15;

-- G6 : Expansion signal - high transaction growth, low adoption ------
--   States growing fast in value but with below-median transactions per user
--   are candidate "growth headroom" regions for further investigation.
WITH latest AS (SELECT MAX(period_key) AS pk FROM state_txn_quarter),
     eng AS (
        SELECT t.state,
               t.txn_amount,
               t.txn_count::DOUBLE / NULLIF(u.registered_users, 0) AS txns_per_user
        FROM state_txn_quarter t
        JOIN state_user_quarter u USING (state, period_key)
        WHERE t.period_key = (SELECT pk FROM latest)
     ),
     yoy AS (
        SELECT state,
               100.0 * (txn_amount - LAG(txn_amount, 4) OVER w)
                     / NULLIF(LAG(txn_amount, 4) OVER w, 0) AS yoy
        FROM state_txn_quarter
        WINDOW w AS (PARTITION BY state ORDER BY period_key)
        QUALIFY period_key = (SELECT pk FROM latest)
     )
SELECT e.state,
       ROUND(y.yoy, 1)              AS yoy_value_pct,
       ROUND(e.txns_per_user, 1)    AS txns_per_user
FROM eng e JOIN yoy y USING (state)
WHERE y.yoy > (SELECT MEDIAN(yoy) FROM yoy)
  AND e.txns_per_user < (SELECT MEDIAN(txns_per_user) FROM eng)
ORDER BY y.yoy DESC;
