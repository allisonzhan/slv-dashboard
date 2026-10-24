"""Rule-based alerts for the dashboard header.

Each check looks only at data up to the latest date and returns zero or one
Alert. Thresholds are deliberately few and explainable in a pitch.
"""

from dataclasses import dataclass

import pandas as pd

WARN, INFO = "warning", "info"

RATIO_EXTREME_PCTILE = 0.90       # ratio in its top/bottom 10% since 2010
POSITIONING_Z = 2.0               # managed-money net %OI vs. trailing 3 years
POSITIONING_LOOKBACK_WEEKS = 156
REGIME_RECENT_WEEKS = 4           # regime changed within this many weeks
BETA_MULTIPLE = 2.0               # rolling copper beta vs. full sample
STALE_DAYS = {"prices": 4, "cot": 10}


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
    return out


def all_alerts(daily: pd.DataFrame, rule_regime: pd.Series, markov_regime: pd.Series | None,
               betas: pd.DataFrame, full_copper_beta: float, window: int,
               today: pd.Timestamp | None = None) -> list[Alert]:
    today = today or pd.Timestamp.today().normalize()
    checks = [
        ratio_extreme(daily),
        positioning_extreme(daily),
        positioning_flip(daily),
        regime_change(rule_regime, "Monetary/industrial"),
        regime_change(markov_regime, "Volatility") if markov_regime is not None else None,
        copper_beta_stretched(betas, full_copper_beta, window),
    ]
    alerts = stale_data(daily, today) + [a for a in checks if a is not None]
    return sorted(alerts, key=lambda a: a.level != WARN)  # warnings first
