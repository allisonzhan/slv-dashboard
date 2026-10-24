"""Streamlit entry point: streamlit run app.py"""

import streamlit as st

from slv_dashboard.config import REGRESSION_WINDOWS_WEEKS
from slv_dashboard.dashboard import charts
from slv_dashboard.dashboard import data as dd
from slv_dashboard.models import alerts

st.set_page_config(page_title="Silver Dashboard", layout="wide")

DRIVER_LABELS = {
    "real_yield_chg": "Real yield (per 1pp)",
    "dollar_ret": "Dollar",
    "copper_ret": "Copper",
}


@st.cache_data(ttl=3600, show_spinner="Loading data")
def load_data() -> dd.DashboardData:
    return dd.load()


def refresh_everything() -> None:
    from slv_dashboard import refresh
    from slv_dashboard.models import report

    with st.spinner("Pulling sources and refitting models (about a minute)"):
        refresh.main()
        report.run()
    load_data.clear()


def chart(fig, table, key: str) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, key=key, config={"displayModeBar": False})
    with st.expander("Table view"):
        st.dataframe(table.sort_index(ascending=False), width="stretch", height=240)


# --- Header and filter row ---------------------------------------------------
st.title("Silver Dashboard")
st.caption("COINS metals division · weekly driver model and fundamentals")

try:
    data = load_data()
except dd.MissingCache as exc:
    st.warning(f"No cached data yet. Run `{exc}` in the project folder, or use the button below.")
    if st.button("Pull data now"):
        refresh_everything()
        st.rerun()
    st.stop()

t = charts.theme_for(st.context.theme.type)
daily = data.daily

f1, f2, f3 = st.columns([3, 2, 1], vertical_alignment="bottom")
range_key = f1.segmented_control("Range", list(dd.RANGES), default="5Y", key="range") or "5Y"
window = f2.segmented_control("Regression window", REGRESSION_WINDOWS_WEEKS, default=52,
                              format_func=lambda w: f"{w} weeks", key="window") or 52
if f3.button("Refresh data", width="stretch"):
    refresh_everything()
    st.rerun()

st.caption(f"Data through {daily.index.max():%b %d, %Y}")

# --- Stat tiles ----------------------------------------------------------------
rule_now = data.rule[window].iloc[-1]
k1, k2, k3, k4, k5 = st.columns(5)
silver_chg = dd.change(daily["silver"], 5)
k1.metric("Silver ($/oz)", f"{daily['silver'].iloc[-1]:,.2f}",
          f"{silver_chg:+.2f} 1w" if silver_chg is not None else None)
ratio_chg = dd.change(daily["gold_silver_ratio"], 5)
k2.metric("Gold/silver ratio", f"{daily['gold_silver_ratio'].iloc[-1]:.1f}",
          f"{ratio_chg:+.1f} 1w" if ratio_chg is not None else None, delta_color="off")
if "mm_net_pct_oi" in daily:
    pos = daily["mm_net_pct_oi"].dropna()
    pos_chg = dd.change(pos.drop_duplicates(), 1)
    k3.metric("Managed money net (% OI)", f"{pos.iloc[-1]:.1f}%",
              f"{pos_chg:+.1f} pts vs prior report" if pos_chg is not None else None, delta_color="off")
k4.metric(f"Regime ({window}w rule)", rule_now["regime"].title(),
          f"copper share {rule_now['share_pctile']:.0%} pctile", delta_color="off",
          help="Copper's share of explanatory power vs. gold, ranked against history. "
               "Top third = industrial, bottom third = monetary.")
if data.markov is not None:
    mk = data.markov.iloc[-1]
    k5.metric("Volatility regime (Markov)", mk["regime"].title(), f"p(stressed) {mk['p_stressed']:.0%}",
              delta_color="off", help="Two-regime Markov-switching model on weekly returns.")

# --- Alerts --------------------------------------------------------------------------
active = alerts.all_alerts(
    daily, data.rule[window]["regime"],
    data.markov["regime"] if data.markov is not None else None,
    data.betas[window], float(data.full_betas["copper_ret"]), window,
)
if active:
    for a in active:
        show = st.warning if a.level == alerts.WARN else st.info
        show(f"**{a.title}.** {a.detail}", icon=":material/warning:" if a.level == alerts.WARN else ":material/info:")
else:
    st.caption("No alerts: ratio, positioning and regimes are all inside normal ranges.")

# --- Price and ratio -------------------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("Silver price")
    s = dd.clip(daily["silver"], range_key)
    chart(charts.line({"Silver": s}, t, y_title="$/oz"), s.to_frame(), "price")
with c2:
    st.subheader("Gold/silver ratio")
    r = dd.clip(daily["gold_silver_ratio"], range_key)
    med = float(daily["gold_silver_ratio"].median())
    chart(charts.line({"Gold/silver ratio": r}, t, hover_format=".1f", ref=med,
                      ref_label=f"2010–now median {med:.0f}"), r.to_frame(), "ratio")

# --- Positioning and inventories -------------------------------------------------
c3, c4 = st.columns(2)
with c3:
    st.subheader("CFTC managed-money positioning")
    if "mm_net_pct_oi" in daily:
        p = dd.clip(daily["mm_net_pct_oi"].dropna(), range_key)
        chart(charts.line({"Net long, % of open interest": p}, t, y_title="% of OI", hover_format=".1f", ref=0),
              daily[["mm_long", "mm_short", "mm_net", "mm_net_pct_oi"]].drop_duplicates().pipe(dd.clip, range_key),
              "cot")
        st.caption("Shown from each Friday release date (positions as of the prior Tuesday).")
with c4:
    st.subheader("COMEX warehouse stocks")
    if {"registered_oz", "eligible_oz"} <= set(daily.columns):
        inv = dd.clip(daily[["registered_oz", "eligible_oz"]].dropna(how="all") / 1e6, range_key)
        chart(charts.line({"Registered": inv["registered_oz"], "Eligible": inv["eligible_oz"]}, t,
                          y_title="million oz", hover_format=",.1f"), inv, "comex")
    else:
        st.info("No COMEX files imported yet. Save CME's `Silver_stocks.xls` from your browser into "
                "`data/imports/`, then press **Refresh data**.")

# --- Macro ---------------------------------------------------------------------------
st.subheader("Macro drivers")
m1, m2 = st.columns(2)
with m1:
    y = dd.clip(daily["real_yield_10y"].dropna(), range_key)
    st.markdown("**10-year real yield (TIPS)**")
    chart(charts.line({"10Y real yield": y}, t, y_title="%", hover_format=".2f", height=220), y.to_frame(), "ry")
with m2:
    d = dd.clip(daily["dollar_broad"].dropna(), range_key)
    st.markdown("**Broad trade-weighted dollar**")
    chart(charts.line({"Dollar index": d}, t, y_title="index", hover_format=".1f", height=220), d.to_frame(), "usd")
if "slv_ounces" in daily and daily["slv_ounces"].notna().any():
    oz = daily["slv_ounces"].dropna()
    st.caption(f"SLV ounces in trust: {oz.iloc[-1] / 1e6:,.1f}M as of {oz.index[-1]:%b %d, %Y} "
               f"(history builds up with each daily refresh)")

# --- Driver sensitivities ------------------------------------------------------------
st.subheader(f"Silver's sensitivity to each driver, rolling {window} weeks")
st.caption("Betas from weekly returns (gold left out, so the monetary channel shows in real yields and the dollar). "
           "Reference line = 2010–now full-sample beta.")
b = dd.clip(data.betas[window], range_key)
panels = {DRIVER_LABELS[c]: b[c] for c in DRIVER_LABELS}
refs = {DRIVER_LABELS[c]: float(data.full_betas[c]) for c in DRIVER_LABELS}
chart(charts.small_multiples(panels, t, refs=refs, ref_label="full sample"),
      b.rename(columns=DRIVER_LABELS), "betas")

# --- Regimes ---------------------------------------------------------------------------
g1, g2 = st.columns(2)
with g1:
    st.subheader("Monetary vs. industrial")
    rr = dd.clip(data.rule[window], range_key)
    chart(charts.percentile_with_bands(rr["share_pctile"], t), rr, "rule")
    st.caption("Copper's share of silver's explained variance, ranked against all earlier windows. "
               "A regime that lasts years drifts toward the middle as it becomes normal.")
with g2:
    st.subheader("Calm vs. stressed")
    if data.markov is not None:
        mk = dd.clip(data.markov, range_key)
        chart(charts.probability_area(mk["p_stressed"], t, name="p(stressed)"), mk, "markov")
        st.caption("Stressed weeks: higher volatility and higher sensitivity to both gold and copper.")
