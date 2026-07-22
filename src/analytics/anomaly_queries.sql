-- =====================================================================
-- anomaly_queries.sql : robust statistical flags for unusual movements.
-- These are SQL-native detectors (robust z-score & IQR) that complement
-- the ML detector in src/modeling/. Outputs are "areas for investigation",
-- not judgements about users or merchants.
-- =====================================================================

-- A1 : Robust z-score of QoQ growth, per state -----------------------
--   Uses median & MAD (median absolute deviation) instead of mean/std so a
--   single outlier quarter doesn't mask the rest. |z| >= 3.5 is the flag.
WITH qoq AS (
    SELECT state, year, quarter, period_key,
           100.0 * (txn_amount - LAG(txn_amount) OVER w)
                 / NULLIF(LAG(txn_amount) OVER w, 0) AS g
    FROM state_txn_quarter
    WINDOW w AS (PARTITION BY state ORDER BY period_key)
),
med AS (   -- per-state median growth
    SELECT state, MEDIAN(g) AS med FROM qoq WHERE g IS NOT NULL GROUP BY state
),
dev AS (   -- absolute deviations from the median
    SELECT q.state, q.year, q.quarter, q.g, m.med, ABS(q.g - m.med) AS abs_dev
    FROM qoq q JOIN med m USING (state) WHERE q.g IS NOT NULL
),
mad AS (   -- median absolute deviation (robust spread)
    SELECT state, MEDIAN(abs_dev) AS mad FROM dev GROUP BY state
),
robust AS (
    SELECT d.state, d.year, d.quarter, d.g,
           0.6745 * (d.g - d.med) / NULLIF(m.mad, 0) AS robust_z
    FROM dev d JOIN mad m USING (state)
)
SELECT state, year, quarter,
       ROUND(g, 1)         AS qoq_pct,
       ROUND(robust_z, 2)  AS robust_z,
       CASE WHEN robust_z > 0 THEN 'spike' ELSE 'drop' END AS direction
FROM robust
WHERE ABS(robust_z) >= 3.5
ORDER BY ABS(robust_z) DESC;

-- A2 : IQR outliers of average ticket size across states (per quarter)
--   Flags states whose value-per-transaction is far from the peer band.
WITH ticket AS (
    SELECT state, period_key, year, quarter,
           txn_amount / NULLIF(txn_count, 0) AS avg_ticket
    FROM state_txn_quarter
),
bounds AS (
    SELECT period_key,
           QUANTILE_CONT(avg_ticket, 0.25) AS q1,
           QUANTILE_CONT(avg_ticket, 0.75) AS q3
    FROM ticket GROUP BY period_key
)
SELECT t.state, t.year, t.quarter,
       ROUND(t.avg_ticket, 1) AS avg_ticket_inr,
       ROUND(b.q1, 1) AS q1, ROUND(b.q3, 1) AS q3,
       CASE WHEN t.avg_ticket > b.q3 + 1.5 * (b.q3 - b.q1) THEN 'high'
            WHEN t.avg_ticket < b.q1 - 1.5 * (b.q3 - b.q1) THEN 'low' END AS flag
FROM ticket t JOIN bounds b USING (period_key)
WHERE t.avg_ticket > b.q3 + 1.5 * (b.q3 - b.q1)
   OR t.avg_ticket < b.q1 - 1.5 * (b.q3 - b.q1)
ORDER BY t.period_key DESC, avg_ticket_inr DESC;

-- A3 : Sudden district-level swings (map panel) ----------------------
--   Large single-quarter jumps at district grain, worth a data-quality or
--   growth look. Filters out tiny-base noise with a volume floor.
WITH d AS (
    SELECT state, district, year, quarter,
           year * 10 + quarter AS period_key, txn_amount
    FROM map_transaction
),
g AS (
    SELECT state, district, year, quarter, txn_amount,
           LAG(txn_amount) OVER w AS prev_amount,
           100.0 * (txn_amount - LAG(txn_amount) OVER w)
                 / NULLIF(LAG(txn_amount) OVER w, 0) AS qoq
    FROM d
    WINDOW w AS (PARTITION BY state, district ORDER BY period_key)
)
SELECT state, district, year, quarter,
       ROUND(qoq, 1) AS qoq_pct,
       ROUND(prev_amount/1e7, 2) AS prev_cr,
       ROUND(txn_amount/1e7, 2)  AS curr_cr
FROM g
WHERE qoq IS NOT NULL
  AND prev_amount > 1e8            -- ignore very small bases (< ~10 cr)
  AND ABS(qoq) >= 60
ORDER BY ABS(qoq) DESC
LIMIT 25;
