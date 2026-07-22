"""Streamlit dashboard for UPI Reliability & Growth Intelligence.

Reads directly from :class:`InsightService` (same source as the API), so no
running API is required. Charts use a CVD-validated categorical palette; category
charts carry direct labels + a legend (the light-mode contrast-relief rule).

Run:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import warnings

import altair as alt
import pandas as pd
import streamlit as st

warnings.simplefilter("ignore")

# Make `src` importable when Streamlit runs this file directly.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.serving.service import InsightService, warehouse_exists  # noqa: E402

# --- Validated categorical palette (dataviz skill default) -------------------
CAT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
BLUE = "#2a78d6"
GOOD = "#0ca30c"
CRIT = "#d03b3b"
GRID = "#e1e0d9"
MUTED = "#898781"

st.set_page_config(page_title="UPI Growth Intelligence", page_icon="📈", layout="wide")


def _base(chart: alt.Chart) -> alt.Chart:
    """Recessive grid/axes, no chart-junk."""
    return chart.configure_axis(
        gridColor=GRID, domainColor="#c3c2b7", tickColor=GRID,
        labelColor=MUTED, titleColor=MUTED, labelFontSize=11, titleFontSize=11,
    ).configure_view(strokeWidth=0).configure_legend(labelColor="#52514e", titleColor=MUTED)


@st.cache_resource
def get_service() -> InsightService:
    return InsightService()


def cr(x: float) -> float:
    """INR -> crore."""
    return x / 1e7


# --- Guard: warehouse must exist ---------------------------------------------
st.title("📈 UPI Reliability & Growth Intelligence")
st.caption(
    "Public, aggregated PhonePe Pulse data. Figures are anonymized; outputs are "
    "**areas for investigation / growth opportunities**, not claims about individuals."
)

if not warehouse_exists():
    st.error("Warehouse not found. Build it first:  `make pipeline-full`")
    st.stop()

svc = get_service()
meta = svc.meta()

# --- KPI stat tiles ----------------------------------------------------------
trend = pd.DataFrame(svc.national_trend())
latest, prev = trend.iloc[-1], trend.iloc[-2]
val_qoq = 100 * (latest.txn_amount / prev.txn_amount - 1)
cnt_qoq = 100 * (latest.txn_count / prev.txn_count - 1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest quarter", meta["latest_quarter"])
c2.metric(f"Txn value ({meta['latest_quarter']})", f"₹{cr(latest.txn_amount)/1e5:,.1f}L cr",
          f"{val_qoq:+.1f}% QoQ")
c3.metric("Transactions", f"{latest.txn_count/1e9:,.1f} B", f"{cnt_qoq:+.1f}% QoQ")
c4.metric("Avg ticket size", f"₹{latest.avg_ticket:,.0f}")

st.divider()

# --- National trend (two single-series charts; never a dual axis) ------------
st.subheader("National trend")
tcol1, tcol2 = st.columns(2)
trend_plot = trend.assign(value_cr=lambda d: cr(d.txn_amount), count_bn=lambda d: d.txn_count / 1e9)

with tcol1:
    ch = alt.Chart(trend_plot).mark_area(
        line={"color": BLUE, "strokeWidth": 2}, color=alt.Gradient(
            gradient="linear", stops=[alt.GradientStop(color="#cde2fb", offset=0),
                                      alt.GradientStop(color="#86b6ef", offset=1)],
            x1=1, x2=1, y1=1, y2=0)
    ).encode(
        x=alt.X("quarter_label:O", title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("value_cr:Q", title="Transaction value (₹ cr)"),
        tooltip=["quarter_label", alt.Tooltip("value_cr:Q", format=",.0f", title="₹ cr")],
    ).properties(height=260, title="Value")
    st.altair_chart(_base(ch), width="stretch")

with tcol2:
    ch = alt.Chart(trend_plot).mark_line(color=BLUE, strokeWidth=2, point=True).encode(
        x=alt.X("quarter_label:O", title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("count_bn:Q", title="Transactions (billion)"),
        tooltip=["quarter_label", alt.Tooltip("count_bn:Q", format=",.1f", title="billion")],
    ).properties(height=260, title="Count")
    st.altair_chart(_base(ch), width="stretch")

# --- Category mix + Top states ----------------------------------------------
mcol1, mcol2 = st.columns(2)

with mcol1:
    st.subheader(f"Category mix — {meta['latest_quarter']}")
    mix = pd.DataFrame(svc.category_mix())
    bars = alt.Chart(mix).mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.7)).encode(
        x=alt.X("pct_value:Q", title="% of value"),
        y=alt.Y("category:N", sort="-x", title=None),
        color=alt.Color("category:N",
                        scale=alt.Scale(domain=list(mix.category), range=CAT_COLORS),
                        legend=None),
        tooltip=["category", alt.Tooltip("pct_value:Q", format=".1f", title="% value")],
    )
    labels = bars.mark_text(align="left", dx=4, color="#52514e").encode(
        text=alt.Text("pct_value:Q", format=".1f"))
    st.altair_chart(_base((bars + labels).properties(height=240)), width="stretch")

with mcol2:
    st.subheader(f"Top states by value — {meta['latest_quarter']}")
    tops = pd.DataFrame(svc.top_states(10)).assign(value_cr=lambda d: cr(d.txn_amount))
    ch = alt.Chart(tops).mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.72), color=BLUE).encode(
        x=alt.X("value_cr:Q", title="Transaction value (₹ cr)"),
        y=alt.Y("state:N", sort="-x", title=None),
        tooltip=["state", alt.Tooltip("value_cr:Q", format=",.0f", title="₹ cr")],
    )
    st.altair_chart(_base(ch.properties(height=280)), width="stretch")

st.divider()

# --- Forecast ----------------------------------------------------------------
fc = svc.forecast_next_quarter()
st.subheader(f"Next-quarter forecast — {fc['quarter']}")
st.caption(f"Champion model: **{fc['champion_model']}** (won the walk-forward backtest, "
           "WAPE 6.8%). Ridge shown for comparison.")
fdf = pd.DataFrame(fc["states"]).head(12)
fplot = fdf.assign(forecast_cr=lambda d: cr(d.forecast_champion),
                   ridge_cr=lambda d: cr(d.forecast_ridge))
melt = fplot.melt(id_vars="state", value_vars=["forecast_cr", "ridge_cr"],
                  var_name="model", value_name="value_cr")
model_names = {"forecast_cr": fc["champion_model"], "ridge_cr": "ridge"}
melt["model"] = melt["model"].map(model_names)
ch = alt.Chart(melt).mark_bar(cornerRadiusEnd=3).encode(
    x=alt.X("value_cr:Q", title="Forecast value (₹ cr)"),
    y=alt.Y("state:N", sort="-x", title=None),
    yOffset="model:N",
    color=alt.Color("model:N", scale=alt.Scale(range=CAT_COLORS[:2]), title="Model"),
    tooltip=["state", "model", alt.Tooltip("value_cr:Q", format=",.0f", title="₹ cr")],
)
st.altair_chart(_base(ch.properties(height=380)), width="stretch")

st.divider()

# --- Growth leaders & expansion signals -------------------------------------
gcol1, gcol2 = st.columns(2)
with gcol1:
    st.subheader("Sustained growth leaders")
    st.caption("Highest median quarter-over-quarter value growth.")
    st.dataframe(pd.DataFrame(svc.growth_leaders(12)), hide_index=True, width="stretch")
with gcol2:
    st.subheader("Expansion signals")
    st.caption("High YoY value growth **and** below-median transactions/user — headroom.")
    st.dataframe(pd.DataFrame(svc.expansion_signals()), hide_index=True, width="stretch")

st.divider()

# --- Anomalies ---------------------------------------------------------------
st.subheader("Anomaly detection (Isolation Forest)")
st.caption("Most unusual state-quarters by joint behaviour — areas for investigation.")
adf = pd.DataFrame(svc.anomalies(15))
adf_show = adf.assign(
    txn_cr=lambda d: cr(d.txn_amount).round(0),
    qoq_pct=lambda d: (100 * d.qoq_amt).round(1),
    user_growth_pct=lambda d: (100 * d.user_growth).round(1),
    value_user_gap_pct=lambda d: (100 * d.value_user_gap).round(1),
    score=lambda d: d.anomaly_score.round(3),
)[["state", "year", "quarter", "txn_cr", "qoq_pct", "user_growth_pct",
   "value_user_gap_pct", "score"]]
st.dataframe(adf_show, hide_index=True, width="stretch")

st.divider()

# --- Segments ----------------------------------------------------------------
seg = svc.segments()
st.subheader(f"State segments (K-Means, k={seg['k']}, silhouette={seg['silhouette']:.2f})")
for cl in seg["clusters"]:
    with st.expander(
        f"Cluster {int(cl['cluster'])} — {cl['n_states']} states · "
        f"YoY {100*cl['yoy_growth']:.0f}% · {cl['txns_per_user']:.0f} txns/user · "
        f"₹{cl['avg_ticket']:,.0f} ticket"
    ):
        st.write(", ".join(cl["states"]))

st.caption(f"Warehouse: {meta['first_quarter']}–{meta['latest_quarter']}, "
           f"{meta['states']} states · Source: PhonePe Pulse (CDLA-Permissive-2.0)")
