# Model Card — State-Level Quarterly Transaction Forecast

## Overview
Forecasts the **next-quarter total UPI transaction value (INR)** for each Indian
state, from PhonePe Pulse public aggregate data. Two learned models are compared
against three time-aware naive baselines under walk-forward validation.

- **Task**: univariate-per-state regression on a 36-state × quarterly panel.
- **Target**: `txn_amount` (state total, all categories), modelled as `log1p`.
- **Unit of observation**: one (state, quarter).
- **Training data**: 2018 Q1 – 2024 Q4 (28 quarters; 24 usable after 1yr of lags).

## Features (all strictly lagged — no leakage)
Lagged log levels (amount & count at t-1, t-2, t-4), a 4-quarter rolling mean,
lagged QoQ/YoY growth, lagged registered-users & engagement ratios
(txns-per-user, app-opens-per-user), lagged category mix (5 shares), and
target-quarter seasonality (`q_sin`, `q_cos`). Every feature for quarter *t* is
computed from data at *t-1* or earlier via `groupby(state).shift(k)` on a
gap-reindexed panel. This is verified by unit tests
(`tests/test_features.py::test_target_never_leaks_into_features`).

## Models
| Model | Notes |
|---|---|
| `naive_last` | random walk: next = last quarter |
| `seasonal_naive` | next = same quarter last year |
| `seasonal_yoy` | seasonal naive × latest YoY growth ratio |
| `ridge` | StandardScaler + Ridge(α=5) on log target |
| `gbm` | HistGradientBoosting (depth 3, 300 trees, lr 0.05, L2 1.0) |

## Validation
**Walk-forward (expanding window).** For each of the last 8 quarters, models are
retrained on *all* strictly-earlier quarters and evaluated on that held-out
quarter. No random splits — that would leak future information in a time series.

## Results (8-quarter holdout, 2023 Q1 – 2024 Q4)
| Model | WAPE | sMAPE | bias |
|---|---|---|---|
| **seasonal_yoy** | **6.76%** | 9.5% | +2.9% |
| ridge | 7.08% | 10.6% | +3.2% |
| naive_last | 8.79% | 11.7% | −7.6% |
| gbm | 14.22% | 12.9% | −6.2% |
| seasonal_naive | 29.21% | 39.3% | −29.2% |

**Headline finding:** a disciplined baseline (`seasonal_yoy`) is the most accurate,
with a regularized linear model within a point of it. The gradient-boosting model
**underperforms** on this short, smooth, strongly-trending panel — a genuine result
worth reporting, not hiding. Error is lowest for large mature states
(Tamil Nadu, Punjab, West Bengal: ~2–3% WAPE) and highest for small volatile ones
(Manipur, Chandigarh), where single-quarter swings dominate.

## Intended use & limitations
- **Intended**: prioritization and trend monitoring on public, aggregated data —
  "where is growth accelerating / decelerating", framed as areas for investigation.
- **Not intended**: any inference about individual users, merchants, or fraud; the
  data is aggregated and anonymized.
- **Limitations**: short history (28 quarters) limits complex models; growth was
  unusually strong over the period, favouring trend-following baselines; district
  and category-level forecasts are future work.

## Companion models
- **Anomaly detection** (`src/modeling/anomaly_detection.py`): Isolation Forest over
  joint behavioural signals (QoQ growth, ticket size, user growth, value-vs-user
  gap) flags unusual *combinations* the univariate SQL flags miss.
- **Segmentation** (`src/modeling/segmentation.py`): K-Means (k chosen by silhouette)
  groups states into behavioural archetypes for regional strategy.

## Reproduce
```bash
make pipeline-full     # load 2018-2024
make backtest          # leaderboard + error tables -> reports/
make anomaly
make segment
make test              # includes leakage tests
```
