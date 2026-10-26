"""Streamlit entry point: streamlit run app.py"""

import pandas as pd
import streamlit as st

from slv_dashboard.analogs import backtest, engine, setups
from slv_dashboard.analogs import features as feat
from slv_dashboard.config import ANALOG_HORIZONS_WEEKS, ANALOG_K, REGRESSION_WINDOWS_WEEKS
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


@st.cache_resource(show_spinner="Preparing analogs")
def analog_context(target: str, through: pd.Timestamp) -> engine.AnalogContext:
    # `through` keys the cache to the data date so a refresh rebuilds it
    return engine.AnalogContext.from_daily(load_data().long_daily, target)


@st.cache_data(show_spinner="Scanning setups")
def setup_scan(target: str, through: pd.Timestamp) -> pd.DataFrame:
    return setups.scan(analog_context(target, through))


def refresh_everything() -> None:
    from slv_dashboard import refresh
    from slv_dashboard.analogs import report as analog_report
    from slv_dashboard.models import report

    with st.spinner("Pulling sources, refitting models and re-running the analog backtest (a few minutes)"):
        refresh.main()
        report.run()
        analog_report.run()
    load_data.clear()
    analog_context.clear()
    setup_scan.clear()


def pct(v, signed: bool = True) -> str:
    return "–" if pd.isna(v) else (f"{v:+.1%}" if signed else f"{v:.0%}")


def chart(fig, table, key: str) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, key=key, config={"displayModeBar": False})
    with st.expander("Table view"):
        st.dataframe(table.sort_index(ascending=False), width="stretch", height=240)


# --- Header and filter row ---------------------------------------------------
st.title("Silver Dashboard")
st.caption("COINS metals division · weekly brief, historical analogs, drivers and fundamentals")

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


def show_alerts() -> None:
    if active:
        for a in active:
            show = st.warning if a.level == alerts.WARN else st.info
            show(f"**{a.title}.** {a.detail}",
                 icon=":material/warning:" if a.level == alerts.WARN else ":material/info:")
    else:
        st.caption("No alerts: ratio, positioning and regimes are all inside normal ranges.")


through = data.long_daily.index.max()
tab_brief, tab_analogs, tab_macro, tab_supply, tab_pos = st.tabs(
    ["Weekly Brief", "Technicals & Analogs", "Macro", "Supply & Flows", "Positioning"])

# === Weekly Brief =====================================================================
with tab_brief:
    show_alerts()
    b1, b2 = st.columns([3, 2])
    with b1:
        st.subheader("What changed this week")
        st.dataframe(dd.weekly_table(daily), width="stretch")
        st.caption("1w/4w change in the series' own units (percentage points for yields and positioning). "
                   "Percentile = where today's level sits since 2010.")
    with b2:
        st.subheader("Analog read (silver futures)")
        res_s = engine.find(analog_context("silver", through))
        if res_s is not None:
            for h in (4, 13):
                o = res_s.outcomes.loc[h]
                st.markdown(f"**{h} weeks:** analogs {pct(o['median'])} median, up {pct(o['hit_rate'], False)} "
                            f"of the time vs. base {pct(o['base_median'])} / {pct(o['base_hit_rate'], False)} "
                            f"(p = {o['p_value']:.2f})")
            top = res_s.matches.head(3)
            st.caption("Closest past setups: " + "; ".join(
                f"{d:%b %Y}" + (f" ({r['episode']})" if r["episode"] else "") for d, r in top.iterrows()))
        if 13 in data.backtests:
            st.caption(f"Track record: {backtest.verdict(backtest.score(data.backtests[13]))}")
        live = setup_scan("silver", through)
        live = live[live["live"] & (live["horizon_weeks"] == 13)] if not live.empty else live
        st.subheader("Live setups")
        if live.empty:
            st.caption("No named setups live this week.")
        for _, r in live.iterrows():
            st.markdown(f"**{r['setup']}** ({r['view']}): {r['n']:.0f} past episodes, 13w median "
                        f"{pct(r['median'])} vs. base {pct(r['base_median'])}, up {pct(r['hit_rate'], False)}")

# === Technicals & Analogs ============================================================
with tab_analogs:
    st.caption("Past weeks that looked most like this one (trend, macro and positioning, plus the shape of "
               "the last 60 days), and what happened next. Every number sits next to the base rate: the "
               "edge is the difference.")
    a1, a2, a3, a4 = st.columns([2, 3, 1, 1], vertical_alignment="bottom")
    target = a1.selectbox("Series", list(feat.TARGETS), format_func=feat.TARGETS.get, key="an_target")
    groups = a2.multiselect("Match on", list(feat.GROUPS), default=list(feat.GROUPS), key="an_groups",
                            format_func=str.title)
    k = a3.number_input("Analogs", 5, 50, ANALOG_K, step=5, key="an_k")
    horizon = a4.selectbox("Horizon", [4, 13, 26], index=1, format_func=lambda h: f"{h} weeks", key="an_h")
    same_regime = st.toggle("Only weeks in the same monetary/industrial regime (52w rule, 2012 on)", key="an_reg")

    ctx = analog_context(target, through)
    regime_filter = None
    if same_regime:
        reg = data.rule[52]["regime"].reindex(ctx.weekly.index, method="ffill")
        regime_filter = reg == reg.iloc[-1]
    res = engine.find(ctx, groups=tuple(groups), k=int(k), candidate_filter=regime_filter)
    if res is None:
        st.info("Not enough comparable history for this combination. Try fewer feature groups or turn off "
                "the regime filter.")
    else:
        o = res.outcomes.loc[horizon]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric(f"Median {horizon}w return", pct(o["median"]), f"{o['edge_median']:+.1%} vs. base",
                  help=f"Base rate median {o['base_median']:+.1%}")
        m2.metric("Up share", pct(o["hit_rate"], False), f"{o['edge_hit_rate']:+.0%} vs. base",
                  help=f"Base rate {o['base_hit_rate']:.0%}")
        m3.metric("Significance", f"p = {o['p_value']:.2f}",
                  "edge unlikely by chance" if o["p_value"] < 0.1 else "could be chance",
                  delta_color="normal" if o["p_value"] < 0.1 else "off",
                  help="Bootstrap: share of random week-sets of the same size with a median this far from base.")
        m4.metric("Typical drawdown (MAE)", pct(o["mae_median"]), f"worst quartile {o['mae_q25']:+.1%}",
                  delta_color="off", help="Median max adverse move inside the window: a starting point for stops.")
        m5.metric("Forward vol", f"{o['fwd_vol_median']:.0%}", f"base {o['base_fwd_vol_median']:.0%}",
                  delta_color="off", help="Median realised vol after the analogs: compare with SLV implied vol.")
        st.caption(f"{len(res.matches)} analogs from {res.n_candidates} candidate weeks · matched on "
                   f"{len(res.features_used)} features as of {res.query_date:%b %d, %Y}")

        f1, f2 = st.columns([3, 2])
        with f1:
            st.subheader("Where the analogs went next")
            hist = feat.target_series(data.long_daily, target).iloc[-120:]
            paths = res.paths.iloc[:horizon * 5 + 1]
            chart(charts.fan_chart(hist, paths, t), paths.rename(columns=lambda d: f"{d:%Y-%m-%d}"), "fan")
        with f2:
            st.subheader("By horizon vs. base rate")
            chart(charts.outcome_bars(res.outcomes, t), res.outcomes, "outcomes")

        st.subheader("The analogs")
        m = res.matches
        table = pd.DataFrame({
            "Episode": m["episode"],
            "Context then": [engine.describe(r) for _, r in m.iterrows()],
            "Shape corr": m["shape_corr"].round(2),
            "Score": m["score"].round(2),
            **{f"{h}w fwd": m[f"fwd_{h}w"].map(pct) for h in ANALOG_HORIZONS_WEEKS if f"fwd_{h}w" in m},
            f"{horizon}w MAE": m[f"mae_{horizon}w"].map(pct),
            f"{horizon}w MFE": m[f"mfe_{horizon}w"].map(pct),
        })
        table.index = table.index.strftime("%Y-%m-%d")
        st.dataframe(table, width="stretch")
        st.caption("Now: " + engine.describe(res.query_features) + ". Lower score = closer match.")

    st.subheader("Setup scanner")
    scan = setup_scan(target, through)
    if not scan.empty:
        sc = scan[scan["horizon_weeks"] == horizon]
        st.dataframe(pd.DataFrame({
            "Live": sc["live"].map({True: "LIVE", False: ""}),
            "Setup": sc["setup"], "Read": sc["view"],
            "Episodes": sc["n"].astype("Int64"),
            "Median": sc["median"].map(pct), "Base": sc["base_median"].map(pct),
            "Up share": sc["hit_rate"].map(lambda v: pct(v, False)),
            "p": sc["p_value"].round(2),
            "Last fired": pd.to_datetime(sc["last_trigger"]).dt.strftime("%Y-%m-%d"),
        }).set_index("Setup"), width="stretch")
        st.caption(f"{horizon}-week outcomes after the first week of each episode. "
                   "Few episodes = anecdote, not evidence.")

    st.subheader("Track record (walk-forward)")
    if target != "silver":
        st.caption("The nightly backtest covers silver futures with the default settings.")
    for h, bt in data.backtests.items():
        sc_ = backtest.score(bt)
        st.markdown(f"**{h} weeks** · {backtest.verdict(sc_)}")
        st.caption(f"{sc_['n']} weekly calls since {bt.index.min():%Y}: direction right "
                   f"{sc_['direction_accuracy']:.0%} vs. {sc_['always_up_accuracy']:.0%} for always-long; "
                   f"avg {h}w return {sc_['mean_when_analogs_up']:+.1%} when analogs said up, "
                   f"{sc_['mean_when_analogs_down']:+.1%} when they said down.")
    if not data.backtests:
        st.caption("Run `python -m slv_dashboard.analogs.report` to compute the backtest.")

    st.subheader("Price, moving averages and RSI")
    tech = dd.clip(feat.technicals(feat.target_series(data.long_daily, target)), range_key)
    chart(charts.technical_chart(tech, t), tech[["price", "sma50", "sma200", "rsi14"]], "tech")

# === Macro ============================================================================
with tab_macro:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Silver price")
        s = dd.clip(daily["silver"], range_key)
        chart(charts.line({"Silver": s}, t, y_title="$/oz"), s.to_frame(), "price")
        st.caption(dd.what_changed(daily["silver"]))
    with c2:
        st.subheader("Gold/silver ratio")
        r = dd.clip(daily["gold_silver_ratio"], range_key)
        med = float(daily["gold_silver_ratio"].median())
        chart(charts.line({"Gold/silver ratio": r}, t, hover_format=".1f", ref=med,
                          ref_label=f"2010–now median {med:.0f}"), r.to_frame(), "ratio")
        st.caption(dd.what_changed(daily["gold_silver_ratio"], ".1f"))

    st.subheader("Rates and the dollar")
    macro_panels = [("real_yield_10y", "10-year real yield (TIPS)", "%", ".2f"),
                    ("nominal_2y", "2-year Treasury (Fed expectations)", "%", ".2f"),
                    ("breakeven_10y", "10-year breakeven inflation", "%", ".2f"),
                    ("dollar_broad", "Broad trade-weighted dollar", "index", ".1f")]
    macro_panels = [mp for mp in macro_panels if mp[0] in daily]
    for row in range(0, len(macro_panels), 2):
        cols = st.columns(2)
        for col, (key, title, unit, fmt) in zip(cols, macro_panels[row:row + 2]):
            with col:
                y = dd.clip(daily[key].dropna(), range_key)
                st.markdown(f"**{title}**")
                chart(charts.line({title: y}, t, y_title=unit, hover_format=fmt, height=220), y.to_frame(), key)
                st.caption(dd.what_changed(daily[key], fmt, "%" if unit == "%" else ""))

    st.subheader(f"Silver's sensitivity to each driver, rolling {window} weeks")
    st.caption("Betas from weekly returns (gold left out, so the monetary channel shows in real yields and the "
               "dollar). Reference line = 2010–now full-sample beta.")
    b = dd.clip(data.betas[window], range_key)
    panels = {DRIVER_LABELS[c]: b[c] for c in DRIVER_LABELS}
    refs = {DRIVER_LABELS[c]: float(data.full_betas[c]) for c in DRIVER_LABELS}
    chart(charts.small_multiples(panels, t, refs=refs, ref_label="full sample"),
          b.rename(columns=DRIVER_LABELS), "betas")

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

# === Supply & Flows ===================================================================
with tab_supply:
    st.subheader("COMEX warehouse stocks")
    if {"registered_oz", "eligible_oz"} <= set(daily.columns):
        inv = dd.clip(daily[["registered_oz", "eligible_oz"]].dropna(how="all") / 1e6, range_key)
        chart(charts.line({"Registered": inv["registered_oz"], "Eligible": inv["eligible_oz"]}, t,
                          y_title="million oz", hover_format=",.1f"), inv, "comex")
    else:
        st.info("No COMEX files imported yet. Save CME's `Silver_stocks.xls` from your browser into "
                "`data/imports/`, then press **Refresh data**.")
    st.subheader("SLV ounces in trust")
    if "slv_ounces" in daily and daily["slv_ounces"].notna().any():
        oz = daily["slv_ounces"].dropna()
        oz = oz[oz.ne(oz.shift())] / 1e6
        chart(charts.line({"SLV ounces": oz}, t, y_title="million oz", hover_format=",.1f", height=220),
              oz.to_frame("million oz"), "slv_oz")
        st.caption(f"{oz.iloc[-1]:,.1f}M oz as of {oz.index[-1]:%b %d, %Y} "
                   "(history builds up with each daily refresh)")

# === Positioning ======================================================================
with tab_pos:
    st.subheader("CFTC managed-money positioning")
    if "mm_net_pct_oi" in daily:
        p = dd.clip(daily["mm_net_pct_oi"].dropna(), range_key)
        chart(charts.line({"Net long, % of open interest": p}, t, y_title="% of OI", hover_format=".1f", ref=0),
              daily[["mm_long", "mm_short", "mm_net", "mm_net_pct_oi"]].drop_duplicates().pipe(dd.clip, range_key),
              "cot")
        st.caption("Shown from each Friday release date (positions as of the prior Tuesday). "
                   + dd.what_changed(daily["mm_net_pct_oi"].drop_duplicates(), ".1f", periods=1))
