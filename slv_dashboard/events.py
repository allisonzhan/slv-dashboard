"""Event catalogue and event studies: "the last N times this kind of thing happened".

The catalogue merges four sources into one table (date, category, type,
title, region, source):

1. a curated seed (slv_dashboard/data/events_seed.csv): wars, attacks,
   sanctions, tariffs, elections, QE and taper, margin hikes, squeezes and
   crises, including the spikes annotated in the GPR dataset;
2. Fed moves, detected from the FRED fed funds target (every hike and cut);
3. market-detected shocks, using only data up to each date:
   - a geopolitical risk spike (weekly GPR in its top 5% of history),
   - an oil spike or crash (+20% / -25% in four weeks),
   - a volatility spike (VIX crossing 35);
4. anything the club adds in data/imports/events.csv (same columns).

Each event type becomes a named setup, so the setup scanner and the News &
Events tab show, for the picked instrument, what happened next against the
base rate, and whether a type fired this week. Event paths give the
day-by-day average move around past events.
"""

import numpy as np
import pandas as pd

from slv_dashboard.analogs.setups import Setup
from slv_dashboard.config import IMPORTS_DIR, ROOT
from slv_dashboard.data import cache, gpr

SEED_FILE = ROOT / "slv_dashboard" / "data" / "events_seed.csv"
MANUAL_FILE = IMPORTS_DIR / "events.csv"
COLUMNS = ["date", "category", "type", "title", "region", "source"]

CATEGORY_LABELS = {
    "fed": "Fed & rates",
    "macro": "Macro data",
    "geopolitics": "Geopolitics",
    "trade": "Trade policy",
    "market": "Flows & market",
    "financial": "Financial stress",
    "supply": "Supply",
}

TYPE_LABELS = {
    "war_onset": "War begins", "war_threat": "War threat", "military_strike": "Military strike",
    "terror_attack": "Terror attack", "terror_threat": "Terror threat", "sanctions": "Sanctions",
    "annexation": "Annexation", "weapons_test": "Weapons test", "election": "Major election",
    "oil_disruption": "Oil supply disruption", "tariff": "Tariff escalation", "currency": "Currency shock",
    "qe": "QE announcement", "taper": "Taper signal", "fed_hike": "Fed hike", "fed_cut": "Fed cut",
    "financial_crisis": "Financial crisis", "bank_failure": "Bank failure", "sovereign_downgrade": "Sovereign downgrade",
    "pandemic": "Pandemic", "margin_hike": "Exchange margin hike", "squeeze": "Physical squeeze",
    "crash": "Metals crash", "gpr_spike": "Geopolitical risk spike", "oil_spike": "Oil spike (+20% in 4w)",
    "oil_crash": "Oil crash (-25% in 4w)", "vol_spike": "Volatility spike (VIX > 35)",
}

# Detector thresholds (each uses only data up to the date it flags)
GPR_SPIKE_PCTILE = 0.95
GPR_MIN_HISTORY_WEEKS = 260
OIL_SPIKE, OIL_CRASH = np.log(1.20), np.log(0.75)
VIX_SPIKE = 35.0
EPISODE_GAP_DAYS = 56          # same as the setups' 8-week episode gap
MIN_EPISODES_FOR_SETUP = 4


def _first_of_episodes(dates: pd.DatetimeIndex, gap_days: int = EPISODE_GAP_DAYS) -> pd.DatetimeIndex:
    out, last = [], None
    for d in dates.sort_values():
        if last is None or (d - last).days >= gap_days:
            out.append(d)
        last = d
    return pd.DatetimeIndex(out)


def seed() -> pd.DataFrame:
    df = pd.read_csv(SEED_FILE, parse_dates=["date"])
    if MANUAL_FILE.exists():
        df = pd.concat([df, pd.read_csv(MANUAL_FILE, parse_dates=["date"]).assign(source="club")])
    return df.reindex(columns=COLUMNS)


def fed_moves(macro: pd.DataFrame | None) -> pd.DataFrame:
    """Every change in the fed funds target (FRED dates are effective dates, usually the day after the decision)."""
    if macro is None:
        return pd.DataFrame(columns=COLUMNS)
    parts = [macro[c].dropna() for c in ("fed_target_old", "fed_target_upper") if c in macro]
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    target = pd.concat(parts).sort_index()
    target = target[~target.index.duplicated(keep="last")]
    chg = target.diff()
    rows = []
    for d, c in chg[chg.abs() >= 0.1].items():
        bp = int(round(c * 100))
        rows.append({"date": d, "category": "fed", "type": "fed_hike" if c > 0 else "fed_cut",
                     "title": f"Fed {'hikes' if c > 0 else 'cuts'} {abs(bp)}bp (target {target[d]:.2f}%)",
                     "region": "United States", "source": "auto: FRED fed funds target"})
    return pd.DataFrame(rows, columns=COLUMNS)


def detected(daily: pd.DataFrame, gpr_daily: pd.DataFrame | None = None) -> pd.DataFrame:
    """Market-detected shocks, flagged on the first day of each episode."""
    rows = []
    if gpr_daily is not None and not gpr_daily.empty:
        g = gpr_daily["gpr"].copy()
        g.index = g.index + gpr.PUBLICATION_LAG     # known the day after the newspapers ran
        weekly = g.resample("W-FRI").mean()
        pctile = weekly.expanding(GPR_MIN_HISTORY_WEEKS).rank(pct=True)
        for d in _first_of_episodes(pctile[pctile >= GPR_SPIKE_PCTILE].index):
            rows.append({"date": d, "category": "geopolitics", "type": "gpr_spike",
                         "title": f"Geopolitical risk spike (weekly GPR {weekly[d]:.0f}, top {1 - pctile[d]:.0%})",
                         "region": "Global", "source": "auto: GPR index"})
    if "oil" in daily:
        oil = daily["oil"].where(daily["oil"] > 0)
        r = np.log(oil).diff(20)
        for typ, mask, word in (("oil_spike", r >= OIL_SPIKE, "up"), ("oil_crash", r <= OIL_CRASH, "down")):
            for d in _first_of_episodes(r[mask].index):
                rows.append({"date": d, "category": "geopolitics" if typ == "oil_spike" else "macro", "type": typ,
                             "title": f"Oil {word} {np.expm1(r[d]):+.0%} in four weeks", "region": "Global",
                             "source": "auto: oil price"})
    if "vix" in daily:
        v = daily["vix"]
        cross = v[(v >= VIX_SPIKE) & (v.shift() < VIX_SPIKE)]
        for d in _first_of_episodes(cross.index):
            rows.append({"date": d, "category": "financial", "type": "vol_spike",
                         "title": f"VIX spikes to {v[d]:.0f}", "region": "Global", "source": "auto: VIX"})
    return pd.DataFrame(rows, columns=COLUMNS)


def catalogue(daily: pd.DataFrame | None = None) -> pd.DataFrame:
    """The full event table, newest first. ``daily`` is the aligned frame (for detected shocks)."""
    parts = [seed(), fed_moves(cache.load("macro"))]
    if daily is not None:
        parts.append(detected(daily, cache.load(gpr.NAME)))
    df = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["category_label"] = df["category"].map(CATEGORY_LABELS).fillna(df["category"])
    df["type_label"] = df["type"].map(TYPE_LABELS).fillna(df["type"])
    return df.sort_values("date", ascending=False).reset_index(drop=True)


def week_mask(index: pd.DatetimeIndex, dates) -> pd.Series:
    """True for weekly rows whose Friday-ending week contains one of ``dates``."""
    weeks = set(pd.DatetimeIndex(dates).to_period("W-FRI"))
    return pd.Series([p in weeks for p in index.to_period("W-FRI")], index=index)


def event_setups(cat: pd.DataFrame, min_episodes: int = MIN_EPISODES_FOR_SETUP) -> list[Setup]:
    """One setup per event type with enough episodes; it fires in the week of each event."""
    out = []
    for typ, g in cat.groupby("type"):
        dates = pd.DatetimeIndex(g["date"])
        if len(_first_of_episodes(dates)) < min_episodes:
            continue
        label = TYPE_LABELS.get(typ, typ)
        out.append(Setup(f"event_{typ}", f"Event: {label}", f"Weeks with a '{label}' event in the catalogue",
                         lambda w, dates=dates: week_mask(w.index, dates), "event", min_gap_weeks=4))
    return out


def paths(price: pd.Series, dates, before: int = 10, after: int = 65) -> pd.DataFrame:
    """Price around each event, indexed by trading days relative to it, as % from the close before the event."""
    price = price.dropna()
    cols = {}
    for d in pd.DatetimeIndex(dates):
        i = price.index.searchsorted(d)              # event day, or the next trading day
        if i - before < 0 or i >= len(price):
            continue
        base = price.iloc[i - 1] if i >= 1 else price.iloc[i]
        seg = price.iloc[i - before:i + after + 1] / base - 1
        s = pd.Series(seg.to_numpy(), index=np.arange(-before, -before + len(seg)))
        cols[d] = s
    out = pd.DataFrame(cols)
    out.index.name = "days_from_event"
    return out


def drift(price: pd.Series, after: int = 65) -> pd.Series:
    """Unconditional average path (the base rate) over the same horizon, for comparison."""
    lr = np.log(price.dropna()).diff().dropna()
    mu = lr.mean()
    return pd.Series(np.expm1(mu * np.arange(0, after + 1)), index=np.arange(0, after + 1))
