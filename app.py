"""Streamlit entry point: streamlit run app.py"""

import pandas as pd
import streamlit as st

from slv_dashboard import catalysts, export
from slv_dashboard.analogs import backtest, engine, setups
from slv_dashboard.analogs import features as feat
from slv_dashboard.config import ANALOG_HORIZONS_WEEKS, ANALOG_K, REGRESSION_WINDOWS_WEEKS
from slv_dashboard.dashboard import charts
from slv_dashboard.dashboard import data as dd
from slv_dashboard.models import alerts, trade, valuation

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


@st.cache_data(show_spinner="Fitting fair value")
def fair_value(through: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = load_data().long_daily
    return valuation.fair_value(d), valuation.gsr_bands(d)


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
    fair_value.clear()


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
through = data.long_daily.index.max()
silver_now = engine.find(analog_context("silver", through))
active = alerts.all_alerts(
    daily, data.rule[window]["regime"],
    data.markov["regime"] if data.markov is not None else None,
    data.betas[window], float(data.full_betas["copper_ret"]), window,
    curve=data.curve, setup_scan=setup_scan("silver", through),
    analog_outcomes=silver_now.outcomes if silver_now is not None else None,
)


def show_alerts() -> None:
    if active:
        for a in active:
            show = st.warning if a.level == alerts.WARN else st.info
            show(f"**{a.title}.** {a.detail}",
                 icon=":material/warning:" if a.level == alerts.WARN else ":material/info:")
    else:
        st.caption("No alerts: ratio, positioning and regimes are all inside normal ranges.")


tab_brief, tab_analogs, tab_macro, tab_supply, tab_pos, tab_val, tab_trade = st.tabs(
    ["Weekly Brief", "Technicals & Analogs", "Macro", "Supply & Flows", "Positioning", "Valuation", "Trade Builder"])
fv, gsr_b = fair_value(through)

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
        res_s = silver_now
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
        st.subheader("Catalysts, next 3 weeks")
        cal = catalysts.upcoming(days=21)
        if cal.empty:
            st.caption("Nothing scheduled. Add events in data/imports/calendar.csv.")
        for _, r in cal.iterrows():
            st.markdown(f"- **{r['date']:%a %b %d}** · {r['event']}")

    st.subheader("Meeting brief")
    st.caption("Exports a one-page brief, a pitch draft and the chart pack to reports/<date>/. The judgment "
               "sections (bottom line, news, talking points) are written by the weekly-brief agent in Claude Code.")
    if st.button("Export brief and chart pack"):
        with st.spinner("Writing the brief and rendering charts"):
            out = export.export()
        st.success(f"Written to {out}")
    reports = sorted(export.REPORTS_DIR.glob("20*")) if export.REPORTS_DIR.exists() else []
    if reports and (reports[-1] / "brief.md").exists():
        latest = reports[-1] / "brief.md"
        with st.expander(f"Latest brief ({reports[-1].name})"):
            text = export.AGENT_RE.sub(lambda m: m.group(2), latest.read_text(encoding="utf-8"))
            st.markdown(text.replace("$", "\\$"))   # \$: pairs of $ would render as math
        st.download_button("Download brief.md", latest.read_bytes(), file_name=f"silver_brief_{reports[-1].name}.md")

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
    st.subheader("Futures curve: is physical metal tight?")
    if data.curve is not None and not data.curve.empty:
        cv = data.curve.dropna(subset=["front", "next"])
        last = cv.iloc[-1]
        q1, q2, q3 = st.columns(3)
        q1.metric(f"Spread {last['front_contract'][:5]} → {last['next_contract'][:5]}", f"{last['spread']:+.3f}",
                  "backwardation" if last["backwardation"] else "contango", delta_color="off")
        q2.metric("Implied financing", f"{last['implied_financing_pct']:.2f}%", delta_color="off",
                  help="ln(next/front) / years between expiries, annualised")
        q3.metric("Implied lease rate", f"{last['implied_lease_pct']:+.2f}%", delta_color="off",
                  help="Fed funds minus implied financing. Rising lease = metal scarce near-term "
                       "(Oct 2025 squeeze). Negative is normal when contango is rich.")
        v1, v2 = st.columns(2)
        with v1:
            ls = cv["implied_lease_pct"].dropna()
            chart(charts.line({"Implied lease rate": ls}, t, y_title="%", hover_format=".2f", height=220, ref=0),
                  cv[["front", "next", "spread", "implied_financing_pct", "implied_lease_pct"]], "lease")
            st.caption("History builds up with each refresh (yfinance only lists live contracts). "
                       "Contract rolls show as jumps.")
        with v2:
            shape_cols = [c for c in ("c1", "c2", "c3", "c4") if c in cv and pd.notna(cv[c].iloc[-1])]
            if shape_cols:
                shape = pd.Series([cv[c].iloc[-1] for c in shape_cols],
                                  index=pd.to_datetime([cv[f"{c}_expiry"].iloc[-1] for c in shape_cols]))
                chart(charts.line({"Curve today": shape}, t, y_title="$/oz", height=220), shape.to_frame("price"),
                      "curve_shape")
                st.caption("Today's curve by contract expiry. Upward slope = contango.")
    else:
        st.caption("No curve data yet: press Refresh data.")

    st.subheader("SLV options: implied vs. what the analogs realised")
    if data.options is not None and not data.options.empty:
        op = data.options.iloc[-1]
        res_vol = silver_now.outcomes.loc[4, "fwd_vol_median"] if silver_now is not None else float("nan")
        o1, o2, o3, o4 = st.columns(4)
        o1.metric(f"ATM IV ({op['days']:.0f}d)", f"{op['atm_iv']:.0%}", delta_color="off")
        o2.metric("Analog realised vol (4w)", f"{res_vol:.0%}",
                  f"IV {'rich' if op['atm_iv'] > res_vol else 'cheap'} by {abs(op['atm_iv'] - res_vol):.0%}",
                  delta_color="off", help="IV above realised favours selling premium or spreads; below favours buying.")
        o3.metric("Skew (10% OTM call − put)", f"{op['skew_call_minus_put']:+.1%}", delta_color="off",
                  help="Positive = upside calls bid over puts: the market is paying for a squeeze.")
        o4.metric("1σ move to expiry", f"±{op['expected_move_pct']:.1%}", delta_color="off")
        st.caption(f"As of {data.options.index[-1]:%b %d}, expiry {op['expiry']}. IV is backed out from bid/ask "
                   "mids, so it only updates when the refresh runs during market hours.")
    else:
        st.caption("No option snapshot yet: run the refresh during US market hours.")

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

# === Valuation ========================================================================
with tab_val:
    st.subheader("Silver vs. what its drivers imply")
    st.markdown(f"**{valuation.read(fv)}**")
    chart(charts.fair_value_chart(dd.clip(fv, range_key), t),
          dd.clip(fv[["silver", "fair_value", "residual_pct", "z", "r2"]], range_key), "fv")
    st.caption("Rolling 3-year regression of log silver on log gold, the 10Y real yield, the log dollar and log "
               f"copper (weekly levels; latest R² {fv['r2'].iloc[-1]:.2f}). The band is ±1 residual σ. Levels "
               "relationships drift, so treat this as 'stretched vs. recent relationships', not an anchor.")
    v1, v2 = st.columns(2)
    with v1:
        st.markdown("**Rich/cheap z-score**")
        z = dd.clip(fv["z"], range_key)
        chart(charts.line({"Fair-value z": z}, t, hover_format="+.1f", height=220, ref=0), z.to_frame(), "fvz")
    with v2:
        st.markdown("**Gold/silver ratio vs. its 3-year range**")
        chart(charts.ratio_bands(dd.clip(gsr_b, range_key), t, height=220), dd.clip(gsr_b, range_key), "gsr_b")
        st.caption(f"Ratio {gsr_b['gsr'].iloc[-1]:.1f}, {gsr_b['pctile'].iloc[-1]:.0%} percentile of the last "
                   "3 years. High = silver cheap vs. gold.")

# === Trade Builder ====================================================================
with tab_trade:
    st.caption("Every lens scored −2 to +2 with its reasoning, then a trade plan whose stop and targets come from "
               "how far silver actually moved after similar setups. A decision aid for club pitches, not advice.")
    bt13 = data.backtests.get(13)
    bt_verdict = backtest.verdict(backtest.score(bt13)) if bt13 is not None else ""
    ctx_now = analog_context("silver", through)
    card = trade.build_scorecard(
        outcomes=silver_now.outcomes if silver_now is not None else None,
        backtest_has_edge=bt_verdict.startswith("Useful"),
        scan=setup_scan("silver", through), fv=fv, features=ctx_now.weekly.iloc[-1], curve=data.curve)
    s1, s2 = st.columns([3, 2])
    with s1:
        st.subheader("Scorecard")
        st.dataframe(card.frame().set_index("Lens"), width="stretch")
    with s2:
        st.metric("Overall", card.stance.title(), f"{card.total:+d} of ±12", delta_color="off",
                  help="Bullish at +3 or more, bearish at −3 or less, otherwise neutral.")
        tb1, tb2 = st.columns(2)
        risk = tb1.number_input("Risk per trade (% of book)", 0.25, 5.0, 1.0, step=0.25, key="tb_risk")
        hz = tb2.selectbox("Horizon", [4, 13, 26], index=1, format_func=lambda h: f"{h} weeks", key="tb_h")
    iv_now = float(data.options["atm_iv"].iloc[-1]) if data.options is not None and not data.options.empty else None
    tp = trade.plan(card, silver_now.outcomes if silver_now is not None else None, float(daily["silver"].iloc[-1]),
                    horizon_weeks=hz, risk_pct=risk, iv=iv_now, gsr_pctile=float(gsr_b["pctile"].iloc[-1]))
    st.subheader("Trade plan")
    st.markdown(f"**{tp.instrument}**. {tp.rationale}")
    if tp.stance != "neutral":
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Entry (SI)", f"${tp.entry:,.2f}")
        p2.metric("Stop", f"${tp.stop:,.2f}", f"{tp.stop / tp.entry - 1:+.1%}", delta_color="off")
        p3.metric("Targets", " / ".join(f"\\${x:,.2f}" for x in tp.targets),  # \$: two $ would render as math
                  f"{tp.reward_risk:.1f}x reward/risk", delta_color="off")
        p4.metric("Size", f"{tp.position_pct_of_book:.0%} of book", f"risks {tp.risk_pct_of_book:.1f}%",
                  delta_color="off", help="For futures or SLV. For an option spread, risk the premium instead.")
    st.markdown("**What would make us wrong:** " + "; ".join(tp.invalidation))

    analog_lines = []
    if silver_now is not None:
        o13 = silver_now.outcomes.loc[13]
        analog_lines.append(f"{len(silver_now.matches)} closest past setups: 13w median {o13['median']:+.1%} vs. "
                            f"base {o13['base_median']:+.1%}, up {o13['hit_rate']:.0%} of the time "
                            f"(p {o13['p_value']:.2f})")
        analog_lines += [f"{d:%b %Y}{' (' + r['episode'] + ')' if r['episode'] else ''}: 13w "
                         f"{r['fwd_13w']:+.1%}" for d, r in silver_now.matches.head(5).iterrows()]
    pitch = trade.pitch_markdown(card, tp, as_of=through, analog_lines=analog_lines,
                                 catalysts=catalysts.upcoming(days=hz * 7), backtest_verdict=bt_verdict)
    with st.expander("Monthly pitch draft (markdown)", expanded=False):
        st.markdown(pitch.replace("$", "\\$"))
    st.download_button("Download pitch draft", pitch, file_name=f"silver_pitch_{through:%Y-%m}.md",
                       mime="text/markdown")
