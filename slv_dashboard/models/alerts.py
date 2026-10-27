"""Rule-based alerts for the dashboard header.

Each check looks only at data up to the latest date and returns zero or one
Alert. Thresholds are deliberately few and explainable in a pitch.
"""

from dataclasses import dataclass

import pandas as pd

from slv_dashboard.models import channels

WARN, INFO = "warning", "info"

RATIO_EXTREME_PCTILE = 0.90       # ratio in its top/bottom 10% since 2010
POSITIONING_Z = 2.0               # managed-money net %OI vs. trailing 3 years
POSITIONING_LOOKBACK_WEEKS = 156
REGIME_RECENT_WEEKS = 4           # regime changed within this many weeks
BETA_MULTIPLE = 2.0               # rolling copper beta vs. full sample
STALE_DAYS = {"prices": 4, "cot": 10}
LEASE_RATE_PCT = 3.0              # implied lease rate that signals tight physical metal
SLV_FLOW_PCT = 1.0                # one-day change in SLV ounces
ANALOG_EDGE = 0.05                # 13w analog median vs. base rate
ANALOG_P = 0.10
GPR_PCTILE = 0.90                 # 4-week average geopolitical risk index vs. history


@dataclass(frozen=True)
class Alert:
    level: str
    title: str
    detail: str


def ratio_extreme(daily: pd.DataFrame) -> Alert | None:
    ratio = daily["gold_silver_ratio"].dropna()
    pct = (ratio <= ratio.iloc[-1]).mean()
    if pct >= RATIO_EXTREME_PCTILE:
        return Alert(WARN, "Gold/silver ratio near historic high",
                     f"{ratio.iloc[-1]:.1f}, {pct:.0%} percentile since {ratio.index[0]:%Y}: silver cheap vs. gold")
    if pct <= 1 - RATIO_EXTREME_PCTILE:
        return Alert(WARN, "Gold/silver ratio near historic low",
                     f"{ratio.iloc[-1]:.1f}, {pct:.0%} percentile since {ratio.index[0]:%Y}: silver rich vs. gold")
    return None


def _reports(daily: pd.DataFrame) -> pd.Series:
    """One value per COT release (the daily frame forward-fills between releases)."""
    s = daily["mm_net_pct_oi"].dropna()
    return s[s.ne(s.shift())]


def positioning_extreme(daily: pd.DataFrame) -> Alert | None:
    if "mm_net_pct_oi" not in daily:
        return None
    reports = _reports(daily).iloc[-POSITIONING_LOOKBACK_WEEKS:]
    if len(reports) < 52:
        return None
    z = (reports.iloc[-1] - reports.mean()) / reports.std()
    if abs(z) >= POSITIONING_Z:
        side = "long" if z > 0 else "short"
        return Alert(WARN, f"Speculative positioning stretched {side}",
                     f"Managed money net {reports.iloc[-1]:.1f}% of OI, z = {z:+.1f} vs. 3 years: crowding risk")
    return None


def positioning_flip(daily: pd.DataFrame) -> Alert | None:
    if "mm_net_pct_oi" not in daily:
        return None
    reports = _reports(daily)
    if len(reports) < 2 or (reports.iloc[-1] > 0) == (reports.iloc[-2] > 0):
        return None
    to = "net long" if reports.iloc[-1] > 0 else "net short"
    return Alert(INFO, f"Managed money flipped {to}",
                 f"{reports.iloc[-2]:+.1f}% → {reports.iloc[-1]:+.1f}% of OI in the latest report")


def regime_change(regime: pd.Series, name: str) -> Alert | None:
    recent = regime.iloc[-(REGIME_RECENT_WEEKS + 1):]
    if recent.nunique() <= 1:
        return None
    changed_at = recent[recent.ne(recent.shift())].index[-1]
    return Alert(INFO, f"{name} regime changed to {recent.iloc[-1]}",
                 f"Since the week of {changed_at:%b %d}, previously {recent.iloc[0]}")


def copper_beta_stretched(betas: pd.DataFrame, full_copper_beta: float, window: int) -> Alert | None:
    latest = float(betas["copper_ret"].iloc[-1])
    if full_copper_beta > 0 and latest >= BETA_MULTIPLE * full_copper_beta:
        return Alert(INFO, "Silver unusually sensitive to copper",
                     f"{window}-week copper beta {latest:.2f} vs. {full_copper_beta:.2f} full sample: "
                     "industrial demand story is driving price")
    return None


def stale_data(daily: pd.DataFrame, today: pd.Timestamp) -> list[Alert]:
    out = []
    last_price = daily["silver"].dropna().index.max()
    if (today - last_price).days > STALE_DAYS["prices"]:
        out.append(Alert(WARN, "Prices are stale", f"Last price {last_price:%b %d}; press Refresh data"))
    if "mm_net_pct_oi" in daily and daily["mm_net_pct_oi"].notna().any():
        # The daily frame forward-fills COT, so find the last release by its last change
        reports = _reports(daily)
        last_cot = reports.index.max()
        if (today - last_cot).days > STALE_DAYS["cot"] + 3:   # +3: release-date shift
            out.append(Alert(WARN, "COT data is stale", f"Last report released {last_cot:%b %d}"))
    return out


def curve_tightness(curve: pd.DataFrame | None) -> Alert | None:
    """Backwardation or a high implied lease rate: physical metal is scarce near-term."""
    if curve is None or curve.empty:
        return None
    last = curve.dropna(subset=["front", "next"]).iloc[-1]
    if bool(last["backwardation"]):
        return Alert(WARN, "Silver futures in backwardation",
                     f"Next contract {last['next']:.2f} below front {last['front']:.2f}: near-term metal is scarce "
                     "(squeeze conditions, as in Oct 2025)")
    lease = last.get("implied_lease_pct")
    if pd.notna(lease) and lease >= LEASE_RATE_PCT:
        return Alert(WARN, "Implied lease rate elevated",
                     f"{lease:.1f}% annualised from the front-next spread: physical market tightening")
    return None


def slv_flow(daily: pd.DataFrame) -> Alert | None:
    if "slv_ounces" not in daily:
        return None
    oz = daily["slv_ounces"].dropna()
    oz = oz[oz.ne(oz.shift())]
    if len(oz) < 2:
        return None
    chg = (oz.iloc[-1] / oz.iloc[-2] - 1) * 100
    if abs(chg) >= SLV_FLOW_PCT:
        side = "inflow" if chg > 0 else "outflow"
        return Alert(INFO, f"Large SLV {side}",
                     f"{chg:+.1f}% ({(oz.iloc[-1] - oz.iloc[-2]) / 1e6:+,.1f}M oz) since {oz.index[-2]:%b %d}")
    return None


def live_setups(scan: pd.DataFrame | None, previously_live: set[str] | None = None) -> list[Alert]:
    """One alert per named setup live this week (new ones flagged)."""
    if scan is None or scan.empty:
        return []
    live = scan[scan["live"] & (scan["horizon_weeks"] == 13)]
    out = []
    for _, r in live.iterrows():
        new = previously_live is not None and r["key"] not in previously_live
        out.append(Alert(INFO, f"{'New setup' if new else 'Setup live'}: {r['setup']}",
                         f"{r['n']:.0f} past episodes, 13w median {r['median']:+.1%} vs. base {r['base_median']:+.1%}"))
    return out


def analog_edge(outcomes: pd.DataFrame | None, horizon: int = 13) -> Alert | None:
    if outcomes is None or horizon not in outcomes.index:
        return None
    o = outcomes.loc[horizon]
    if abs(o["edge_median"]) >= ANALOG_EDGE and o["p_value"] <= ANALOG_P:
        side = "higher" if o["edge_median"] > 0 else "lower"
        return Alert(INFO, f"Historical analogs lean {side}",
                     f"{horizon}w median {o['median']:+.1%} vs. base {o['base_median']:+.1%} (p = {o['p_value']:.2f}). "
                     "Check the track record before leaning on it.")
    return None


def geopolitical_risk(daily: pd.DataFrame) -> Alert | None:
    """4-week average GPR index in the top decile of its history (data from 2000 in the aligned frame)."""
    if "gpr" not in daily or daily["gpr"].dropna().empty:
        return None
    g = daily["gpr"].rolling(20, min_periods=10).mean().dropna()
    last = g.iloc[-1]
    pct = float((g < last).mean() + 0.5 * (g == last).mean())   # mid-rank: a flat history isn't "extreme"
    if pct >= GPR_PCTILE:
        return Alert(WARN, "Geopolitical risk elevated",
                     f"4-week average GPR {g.iloc[-1]:.0f}, {pct:.0%} percentile: check whether metals are getting "
                     "a haven bid or an oil/inflation shock (News & Events tab)")
    return None


def shock_channel(channel_row: pd.Series | None) -> Alert | None:
    """The market is trading a clear shock channel this week (models/channels.py)."""
    if channel_row is None or not isinstance(channel_row.get("channel"), str) or channel_row["channel"] == "quiet":
        return None
    ch = channel_row["channel"]
    return Alert(INFO, f"Market trading as a {ch.replace('_', ' ')} shock",
                 f"{channels.DESCRIPTIONS[ch]} (score {channel_row['channel_score']:.1f}); "
                 f"usual read for metals: {channels.METALS_READ[ch]}")


def all_alerts(daily: pd.DataFrame, rule_regime: pd.Series, markov_regime: pd.Series | None,
               betas: pd.DataFrame, full_copper_beta: float, window: int,
               today: pd.Timestamp | None = None, curve: pd.DataFrame | None = None,
               setup_scan: pd.DataFrame | None = None, analog_outcomes: pd.DataFrame | None = None,
               channel_row: pd.Series | None = None) -> list[Alert]:
    today = today or pd.Timestamp.today().normalize()
    checks = [
        ratio_extreme(daily),
        positioning_extreme(daily),
        positioning_flip(daily),
        regime_change(rule_regime, "Monetary/industrial"),
        regime_change(markov_regime, "Volatility") if markov_regime is not None else None,
        copper_beta_stretched(betas, full_copper_beta, window),
        curve_tightness(curve),
        slv_flow(daily),
        analog_edge(analog_outcomes),
        geopolitical_risk(daily),
        shock_channel(channel_row),
    ]
    alerts = stale_data(daily, today) + [a for a in checks if a is not None] + live_setups(setup_scan)
    return sorted(alerts, key=lambda a: a.level != WARN)  # warnings first
