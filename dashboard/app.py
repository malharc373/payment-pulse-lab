"""Streamlit dashboard for UPI Reliability & Growth Intelligence.

Reads directly from :class:`InsightService` (same source as the API). Chrome
follows a neutral shadcn/ui-style system; charts use a CVD-validated categorical
palette and a single-hue sequential blue for magnitude. Organised into tabs:
Overview, Forecasts, Map, Explore, Signals.

Run:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import altair as alt
import pandas as pd
import plotly.express as px
import streamlit as st

warnings.simplefilter("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# On Streamlit Community Cloud, deploy-time config arrives as st.secrets. Bridge
# any scalar secrets into os.environ so the pipeline/config (which read env vars,
# e.g. PULSE_AUTO_BUILD / PULSE_DB_PATH) pick them up without a Streamlit dep.
import os  # noqa: E402

try:
    for _k, _v in dict(st.secrets).items():
        if isinstance(_v, (str, int, float, bool)):
            os.environ.setdefault(_k, str(_v))
except Exception:
    pass  # no secrets file locally — fine

from src.serving import geo  # noqa: E402
from src.serving.service import InsightService, warehouse_exists  # noqa: E402

# --- Design tokens -----------------------------------------------------------
CAT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
SEQ_BLUE = ["#eaf2fd", "#b7d3f6", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, BORDER, GRID = "#09090b", "#71717a", "#e4e4e7", "#ececee"

st.set_page_config(page_title="UPI Growth Intelligence", layout="wide")

CSS = f"""
<style>
:root {{ --ink:{INK}; --muted:{MUTED}; --border:{BORDER}; --accent:{BLUE}; }}
html, body, [class*="css"], .stMarkdown, .stMetric {{
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}}
.block-container {{ padding-top: 2.1rem; padding-bottom: 3rem; max-width: 1200px; }}
#MainMenu, footer, header[data-testid="stHeader"] {{ visibility: hidden; height: 0; }}
.masthead h1 {{ font-size: 1.9rem; font-weight: 680; letter-spacing:-.025em; color:var(--ink);
  margin:0 0 .35rem 0; line-height:1.15; }}
.masthead p {{ color:var(--muted); font-size:.95rem; margin:0; max-width:64ch; }}
.pill {{ display:inline-flex; align-items:center; gap:.4rem; font-size:.72rem; color:var(--muted);
  border:1px solid var(--border); border-radius:999px; padding:.2rem .6rem; margin-top:.7rem; background:#fafafa; }}
.pill .dot {{ width:6px; height:6px; border-radius:999px; background:#1baf7a; }}
.eyebrow {{ text-transform:uppercase; letter-spacing:.12em; font-size:.7rem; font-weight:600;
  color:var(--muted); margin:0 0 .1rem 0; }}
.sec-title {{ font-size:1.12rem; font-weight:640; letter-spacing:-.01em; color:var(--ink); margin:0 0 .1rem 0; }}
.sec-sub {{ color:var(--muted); font-size:.85rem; margin:0 0 .4rem 0; line-height:1.4; }}
div[data-testid="stMetric"] {{ background:#fff; border:1px solid var(--border); border-radius:14px;
  padding:1rem 1.15rem; box-shadow:0 1px 2px rgba(9,9,11,.04); }}
div[data-testid="stMetric"] label p {{ color:var(--muted); font-size:.8rem; font-weight:500; }}
div[data-testid="stMetricValue"] {{ font-weight:660; letter-spacing:-.02em; color:var(--ink); }}
hr {{ border-color:var(--border); margin:1.5rem 0; }}
div[data-testid="stDataFrame"] {{ border:1px solid var(--border); border-radius:12px; overflow:hidden; }}
div[data-testid="stExpander"] {{ border:1px solid var(--border); border-radius:12px; }}
button[data-baseweb="tab"] {{ font-weight:550; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def section(eyebrow: str, title: str, sub: str | None = None) -> None:
    html = f'<div class="eyebrow">{eyebrow}</div><div class="sec-title">{title}</div>'
    if sub:
        html += f'<div class="sec-sub">{sub}</div>'
    st.markdown(html, unsafe_allow_html=True)


def base_chart(chart: alt.Chart) -> alt.Chart:
    return chart.configure_axis(
        gridColor=GRID, domainColor=BORDER, tickColor=BORDER,
        labelColor=MUTED, titleColor=MUTED, labelFontSize=11, titleFontSize=11,
    ).configure_view(strokeWidth=0).configure_legend(
        labelColor="#52525b", titleColor=MUTED
    ).configure_title(color=INK, fontSize=12, fontWeight=600, anchor="start")


@st.cache_resource
def get_service() -> InsightService:
    return InsightService()


def cr(x: float) -> float:
    return x / 1e7


# --- Guard -------------------------------------------------------------------
def _bootstrap_warehouse() -> bool:
    """On hosts without a pipeline step (e.g. Streamlit Cloud), build on first run
    when PULSE_AUTO_BUILD=1. NOT cached: a transient failure (e.g. a GitHub API
    timeout) must not be memoized — a reload should retry. Once built,
    ``warehouse_exists()`` short-circuits so no rebuild happens."""
    if warehouse_exists():
        return True
    if os.getenv("PULSE_AUTO_BUILD", "0") in ("1", "true", "True"):
        try:
            with st.spinner("Building the warehouse from PhonePe Pulse (first run only)…"):
                from scripts.run_pipeline import main as run_pipeline

                run_pipeline([
                    "--min-year", os.getenv("PULSE_MIN_YEAR", "2020"),
                    "--max-year", os.getenv("PULSE_MAX_YEAR", "2024"),
                ])
        except Exception as exc:  # noqa: BLE001 - surface, don't crash the app
            st.error(
                f"Warehouse build failed ({type(exc).__name__}: {exc}). This is "
                "usually a transient GitHub API timeout — reload to retry. Setting a "
                "`GITHUB_TOKEN` secret avoids the rate/timeout limits."
            )
            return False
    return warehouse_exists()


if not _bootstrap_warehouse():
    if os.getenv("PULSE_AUTO_BUILD", "0") not in ("1", "true", "True"):
        st.error("Warehouse not found. Set `PULSE_AUTO_BUILD=1` to build on first load, "
                 "or run `make pipeline-full` locally.")
    st.stop()

svc = get_service()

# Guard against a partial deploy (dashboard newer than service) — show a clear
# message instead of a cryptic AttributeError deep inside a tab.
_required = ["available_quarters", "state_map_metrics", "forecast_categories", "forecast_districts"]
_missing = [m for m in _required if not hasattr(svc, m)]
if _missing:
    st.error(
        "The running service is stale (missing: "
        f"{', '.join(_missing)}). This happens after a code update because the host "
        "hot-reloads the script but keeps old modules in memory. **Reboot the app** "
        "(Manage app → Reboot) — a hot-reload or another push will not clear it."
    )
    st.stop()

meta = svc.meta()

st.markdown(
    f"""
    <div class="masthead">
      <h1>UPI Reliability &amp; Growth Intelligence</h1>
      <p>Where digital-payment adoption is accelerating across India — growth,
         forecasts, anomalies and regional segments on public PhonePe Pulse data.
         Figures are aggregated and anonymized; outputs are areas for investigation,
         not claims about individuals.</p>
      <span class="pill"><span class="dot"></span>
        PhonePe Pulse open dataset · {meta['first_quarter']}–{meta['latest_quarter']} · {meta['states']} states</span>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_overview, tab_quarter, tab_forecast, tab_map, tab_explore, tab_signals = st.tabs(
    ["Overview", "By quarter", "Forecasts", "Map", "Explore state", "Signals"]
)

# =============================================================================
# OVERVIEW
# =============================================================================
with tab_overview:
    trend = pd.DataFrame(svc.national_trend())
    latest, prev = trend.iloc[-1], trend.iloc[-2]
    val_qoq = 100 * (latest.txn_amount / prev.txn_amount - 1)
    cnt_qoq = 100 * (latest.txn_count / prev.txn_count - 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest quarter", meta["latest_quarter"])
    c2.metric("Transaction value", f"Rs {cr(latest.txn_amount)/1e5:,.1f}L cr", f"{val_qoq:+.1f}% QoQ")
    c3.metric("Transactions", f"{latest.txn_count/1e9:,.1f} B", f"{cnt_qoq:+.1f}% QoQ")
    c4.metric("Avg ticket size", f"Rs {latest.avg_ticket:,.0f}")

    st.markdown("<hr/>", unsafe_allow_html=True)
    section("Trend", "National transaction volume",
            "Value and count shown separately — never on one dual axis.")
    tp = trend.assign(value_cr=lambda d: cr(d.txn_amount), count_bn=lambda d: d.txn_count / 1e9)
    a, b = st.columns(2)
    with a:
        ch = alt.Chart(tp).mark_area(
            line={"color": BLUE, "strokeWidth": 2},
            color=alt.Gradient(gradient="linear",
                stops=[alt.GradientStop(color="#eaf2fd", offset=0),
                       alt.GradientStop(color="#b7d3f6", offset=1)], x1=1, x2=1, y1=1, y2=0),
        ).encode(
            x=alt.X("quarter_label:O", title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("value_cr:Q", title="Value (Rs cr)"),
            tooltip=["quarter_label", alt.Tooltip("value_cr:Q", format=",.0f", title="Rs cr")],
        ).properties(height=250, title="Value")
        st.altair_chart(base_chart(ch), width="stretch")
    with b:
        ch = alt.Chart(tp).mark_line(color=BLUE, strokeWidth=2, point=True).encode(
            x=alt.X("quarter_label:O", title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("count_bn:Q", title="Transactions (billion)"),
            tooltip=["quarter_label", alt.Tooltip("count_bn:Q", format=",.1f", title="billion")],
        ).properties(height=250, title="Count")
        st.altair_chart(base_chart(ch), width="stretch")

    st.markdown("<hr/>", unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        section("Mix", f"Payment categories · {meta['latest_quarter']}", "Share of total value.")
        mix = pd.DataFrame(svc.category_mix())
        bars = alt.Chart(mix).mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.68)).encode(
            x=alt.X("pct_value:Q", title="% of value"), y=alt.Y("category:N", sort="-x", title=None),
            color=alt.Color("category:N", scale=alt.Scale(domain=list(mix.category), range=CAT_COLORS), legend=None),
            tooltip=["category", alt.Tooltip("pct_value:Q", format=".1f", title="% value")])
        labels = bars.mark_text(align="left", dx=4, color="#52525b").encode(text=alt.Text("pct_value:Q", format=".1f"))
        st.altair_chart(base_chart((bars + labels).properties(height=240)), width="stretch")
    with b:
        section("Leaders", f"Top states by value · {meta['latest_quarter']}", " ")
        tops = pd.DataFrame(svc.top_states(10)).assign(value_cr=lambda d: cr(d.txn_amount))
        ch = alt.Chart(tops).mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.7), color=BLUE).encode(
            x=alt.X("value_cr:Q", title="Value (Rs cr)"), y=alt.Y("state:N", sort="-x", title=None),
            tooltip=["state", alt.Tooltip("value_cr:Q", format=",.0f", title="Rs cr")])
        st.altair_chart(base_chart(ch.properties(height=270)), width="stretch")

# =============================================================================
# BY QUARTER (time-travel)
# =============================================================================
with tab_quarter:
    quarters = svc.available_quarters()
    labels = [q["label"] for q in quarters]
    sel = st.selectbox("Quarter", labels, index=len(labels) - 1)
    pk = int(next(q["period_key"] for q in quarters if q["label"] == sel))

    qtrend = pd.DataFrame(svc.national_trend())
    qtrend["pk"] = qtrend.year * 10 + qtrend.quarter
    row = qtrend[qtrend.pk == pk].iloc[0]
    prior = qtrend[qtrend.pk < pk].tail(1)

    section("Snapshot", f"Quarter {sel}",
            "National totals and regional breakdown for the selected quarter.")
    q1, q2, q3 = st.columns(3)
    if not prior.empty:
        p = prior.iloc[0]
        q1.metric("Transaction value", f"Rs {cr(row.txn_amount)/1e5:,.1f}L cr",
                  f"{100*(row.txn_amount/p.txn_amount-1):+.1f}% QoQ")
        q2.metric("Transactions", f"{row.txn_count/1e9:,.1f} B",
                  f"{100*(row.txn_count/p.txn_count-1):+.1f}% QoQ")
    else:
        q1.metric("Transaction value", f"Rs {cr(row.txn_amount)/1e5:,.1f}L cr")
        q2.metric("Transactions", f"{row.txn_count/1e9:,.1f} B")
    q3.metric("Avg ticket size", f"Rs {row.avg_ticket:,.0f}")

    st.markdown("<hr/>", unsafe_allow_html=True)
    qa, qb = st.columns(2)
    with qa:
        section("Leaders", f"Top states · {sel}", " ")
        tops = pd.DataFrame(svc.top_states(10, period_key=pk)).assign(value_cr=lambda d: cr(d.txn_amount))
        ch = alt.Chart(tops).mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.7), color=BLUE).encode(
            x=alt.X("value_cr:Q", title="Value (Rs cr)"), y=alt.Y("state:N", sort="-x", title=None),
            tooltip=["state", alt.Tooltip("value_cr:Q", format=",.0f", title="Rs cr")])
        st.altair_chart(base_chart(ch.properties(height=280)), width="stretch")
    with qb:
        section("Mix", f"Category mix · {sel}", "Share of transaction value.")
        mix = pd.DataFrame(svc.category_mix(pk))
        bars = alt.Chart(mix).mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.68)).encode(
            x=alt.X("pct_value:Q", title="% of value"), y=alt.Y("category:N", sort="-x", title=None),
            color=alt.Color("category:N", scale=alt.Scale(domain=list(mix.category), range=CAT_COLORS), legend=None),
            tooltip=["category", alt.Tooltip("pct_value:Q", format=".1f", title="% value")])
        labels_c = bars.mark_text(align="left", dx=4, color="#52525b").encode(text=alt.Text("pct_value:Q", format=".1f"))
        st.altair_chart(base_chart((bars + labels_c).properties(height=240)), width="stretch")

    st.markdown("<hr/>", unsafe_allow_html=True)
    section("Geography", f"State choropleth · {sel}", "Transaction value in the selected quarter.")
    qmap = pd.DataFrame(svc.state_map_metrics(pk))
    qmap["st_nm"] = qmap["state"].map(geo.slug_to_stnm)
    qmap["value_cr"] = cr(qmap["txn_amount"])
    qfig = px.choropleth(
        qmap.dropna(subset=["st_nm"]), geojson=geo.load_geojson(),
        featureidkey=geo.FEATURE_ID_KEY, locations="st_nm", color="value_cr",
        color_continuous_scale=SEQ_BLUE, labels={"value_cr": "Value (Rs cr)"},
        hover_name="state", hover_data={"st_nm": False, "value_cr": ":,.1f"})
    qfig.update_geos(fitbounds="locations", visible=False)
    qfig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0),
                       coloraxis_colorbar=dict(title="Rs cr", thickness=12),
                       paper_bgcolor="rgba(0,0,0,0)", font=dict(color=INK))
    st.plotly_chart(qfig, width="stretch", config={"displayModeBar": False})

# =============================================================================
# FORECASTS
# =============================================================================
with tab_forecast:
    fc = svc.forecast_next_quarter()
    section("Forecast", f"Next-quarter state outlook · {fc['quarter']}",
            f"Champion model **{fc['champion_model']}** (walk-forward WAPE 6.8%). "
            "Bars show the point forecast; whiskers the 10–90% prediction interval.")
    fdf = pd.DataFrame(fc["states"]).head(14)
    fp = fdf.assign(champ=lambda d: cr(d.forecast_champion), lo=lambda d: cr(d.forecast_lo),
                    hi=lambda d: cr(d.forecast_hi))
    order = fp.sort_values("champ", ascending=False)["state"].tolist()
    rule = alt.Chart(fp).mark_rule(color=MUTED, strokeWidth=1.5).encode(
        y=alt.Y("state:N", sort=order, title=None),
        x=alt.X("lo:Q", title="Forecast value (Rs cr)"), x2="hi:Q")
    pt = alt.Chart(fp).mark_point(filled=True, color=BLUE, size=80).encode(
        y=alt.Y("state:N", sort=order, title=None), x="champ:Q",
        tooltip=["state", alt.Tooltip("champ:Q", format=",.0f", title="forecast"),
                 alt.Tooltip("lo:Q", format=",.0f", title="low"),
                 alt.Tooltip("hi:Q", format=",.0f", title="high")])
    st.altair_chart(base_chart((rule + pt).properties(height=440)), width="stretch")

    st.markdown("<hr/>", unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        section("Categories", f"Fastest-growing category forecasts · {fc['quarter']}",
                "Ranked by projected growth vs last quarter.")
        cat = pd.DataFrame(svc.forecast_categories(60)["rows"])
        cat = cat.sort_values("growth_vs_last_pct", ascending=False).head(12)
        show = cat.assign(forecast_cr=lambda d: cr(d.forecast_champion).round(0),
                          growth_pct=lambda d: d.growth_vs_last_pct.round(1))
        st.dataframe(show[["state", "category", "forecast_cr", "growth_pct"]],
                     hide_index=True, width="stretch")
    with b:
        if meta.get("districts_available"):
            section("Districts", f"Top district forecasts · {fc['quarter']}", "Highest projected value.")
            dist = pd.DataFrame(svc.forecast_districts(15)["rows"])
            show = dist.assign(forecast_cr=lambda d: cr(d.forecast_champion).round(0),
                               growth_pct=lambda d: d.growth_vs_last_pct.round(1))
            st.dataframe(show[["state", "district", "forecast_cr", "growth_pct"]],
                         hide_index=True, width="stretch")
        else:
            section("Districts", "District forecasts",
                    "Not enabled on this lightweight deployment.")
            st.caption(
                "District-grain forecasts (700+ districts) are turned off here to fit a "
                "free-tier host. The same leakage-free model runs them when deployed with "
                "full ingestion — state and category forecasts above are unaffected.")

# =============================================================================
# MAP
# =============================================================================
with tab_map:
    section("Geography", "State choropleth", "Colour by latest quarter's value or year-over-year growth.")
    metric = st.radio("Metric", ["Transaction value", "YoY growth"], horizontal=True, label_visibility="collapsed")
    mdf = pd.DataFrame(svc.state_map_metrics())
    mdf["st_nm"] = mdf["state"].map(geo.slug_to_stnm)
    mdf["value_cr"] = cr(mdf["txn_amount"])
    col = "value_cr" if metric == "Transaction value" else "yoy_pct"
    label = "Value (Rs cr)" if metric == "Transaction value" else "YoY growth (%)"
    fig = px.choropleth(
        mdf.dropna(subset=["st_nm"]), geojson=geo.load_geojson(),
        featureidkey=geo.FEATURE_ID_KEY, locations="st_nm", color=col,
        color_continuous_scale=SEQ_BLUE, labels={col: label},
        hover_name="state", hover_data={"st_nm": False, col: ":,.1f"},
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0),
                      coloraxis_colorbar=dict(title=label, thickness=12),
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color=INK))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# =============================================================================
# EXPLORE STATE (drill-down)
# =============================================================================
with tab_explore:
    state = st.selectbox("State", svc.states(), index=svc.states().index("karnataka")
                         if "karnataka" in svc.states() else 0)
    detail = svc.state_detail(state)
    f = detail["forecast"]
    section("Drill-down", state.replace("-", " ").title(),
            f"Cluster {detail['cluster']} · next quarter {f['quarter'] if f else 'n/a'}")
    if f:
        m1, m2, m3 = st.columns(3)
        m1.metric("Forecast (next Q)", f"Rs {cr(f['forecast_champion']):,.0f} cr", f"{f['growth_vs_last_pct']:+.1f}% vs last")
        m2.metric("Interval (10–90%)", f"Rs {cr(f['forecast_lo']):,.0f} – {cr(f['forecast_hi']):,.0f} cr")
        m3.metric("Last actual", f"Rs {cr(f['last_actual']):,.0f} cr")

    hist = pd.DataFrame(detail["history"]).assign(value_cr=lambda d: cr(d.txn_amount), kind="actual")
    if f:
        fut_row = pd.DataFrame([{
            "quarter_label": f["quarter"], "value_cr": cr(f["forecast_champion"]),
            "lo": cr(f["forecast_lo"]), "hi": cr(f["forecast_hi"]), "kind": "forecast"}])
    else:
        fut_row = pd.DataFrame()
    combo = pd.concat([hist, fut_row], ignore_index=True)
    domain = combo["quarter_label"].tolist()

    line = alt.Chart(hist).mark_line(color=BLUE, strokeWidth=2, point=True).encode(
        x=alt.X("quarter_label:O", sort=domain, title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("value_cr:Q", title="Value (Rs cr)"),
        tooltip=["quarter_label", alt.Tooltip("value_cr:Q", format=",.0f", title="Rs cr")])
    layers = [line]
    if f:
        band = alt.Chart(fut_row).mark_rule(color=ORANGE, strokeWidth=1.5).encode(
            x=alt.X("quarter_label:O", sort=domain), y="lo:Q", y2="hi:Q")
        fpt = alt.Chart(fut_row).mark_point(filled=True, color=ORANGE, size=90).encode(
            x=alt.X("quarter_label:O", sort=domain), y="value_cr:Q",
            tooltip=[alt.Tooltip("value_cr:Q", format=",.0f", title="forecast")])
        layers += [band, fpt]
    st.altair_chart(base_chart(alt.layer(*layers).properties(height=300)), width="stretch")

    if detail["anomalies"]:
        section("Signals", "Notable quarters", "Highest anomaly scores for this state.")
        adf = pd.DataFrame(detail["anomalies"]).assign(
            qoq_pct=lambda d: (100 * d.qoq_amt).round(1),
            value_user_gap_pct=lambda d: (100 * d.value_user_gap).round(1),
            score=lambda d: d.anomaly_score.round(3))
        st.dataframe(adf[["year", "quarter", "qoq_pct", "value_user_gap_pct", "score"]],
                     hide_index=True, width="stretch")

# =============================================================================
# SIGNALS (growth, anomalies, segments)
# =============================================================================
with tab_signals:
    a, b = st.columns(2)
    with a:
        section("Momentum", "Sustained growth leaders", "Highest median QoQ value growth.")
        st.dataframe(pd.DataFrame(svc.growth_leaders(12)), hide_index=True, width="stretch")
    with b:
        section("Opportunity", "Expansion signals",
                "High YoY value growth with below-median transactions per user.")
        st.dataframe(pd.DataFrame(svc.expansion_signals()), hide_index=True, width="stretch")

    st.markdown("<hr/>", unsafe_allow_html=True)
    section("Anomalies", "Isolation Forest · state-quarters",
            "Most unusual by joint behaviour — areas for investigation.")
    adf = pd.DataFrame(svc.anomalies(15)).assign(
        txn_cr=lambda d: cr(d.txn_amount).round(0),
        qoq_pct=lambda d: (100 * d.qoq_amt).round(1),
        user_growth_pct=lambda d: (100 * d.user_growth).round(1),
        value_user_gap_pct=lambda d: (100 * d.value_user_gap).round(1),
        score=lambda d: d.anomaly_score.round(3))
    st.dataframe(adf[["state", "year", "quarter", "txn_cr", "qoq_pct",
                      "user_growth_pct", "value_user_gap_pct", "score"]],
                 hide_index=True, width="stretch")

    st.markdown("<hr/>", unsafe_allow_html=True)
    seg = svc.segments()
    section("Segments", f"Regional archetypes · K-Means (k={seg['k']})",
            f"Silhouette {seg['silhouette']:.2f}. Grouped by growth, engagement, ticket and mix.")
    for cl in seg["clusters"]:
        with st.expander(
            f"Cluster {int(cl['cluster'])}  ·  {cl['n_states']} states  ·  "
            f"YoY {100*cl['yoy_growth']:.0f}%  ·  {cl['txns_per_user']:.0f} txns/user  ·  "
            f"Rs {cl['avg_ticket']:,.0f} ticket"):
            st.write(", ".join(cl["states"]))

st.markdown(
    f'<p class="sec-sub" style="margin-top:1.5rem">Source: PhonePe Pulse open dataset '
    f'(CDLA-Permissive-2.0) · {meta["first_quarter"]}–{meta["latest_quarter"]} · {meta["states"]} states</p>',
    unsafe_allow_html=True,
)
