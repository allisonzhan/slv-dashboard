"""Load cached data and model outputs for the dashboard."""

from dataclasses import dataclass

import pandas as pd
import requests

from slv_dashboard.config import (CACHE_DIR, DATA_SOURCE, HISTORY_START, HTTP_HEADERS, HTTP_TIMEOUT,
                                  PUBLISHED_DATA_URL, REGRESSION_WINDOWS_WEEKS)
from slv_dashboard.data import cache, dataset
from slv_dashboard.models import drivers

RANGES = {"1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10, "All": None}


@dataclass
class DashboardData:
    daily: pd.DataFrame
    betas: dict[int, pd.DataFrame]          # window (weeks) -> rolling macro betas
    rule: dict[int, pd.DataFrame]           # window (weeks) -> rule-based regime
    markov: pd.DataFrame | None
    full_betas: pd.Series                   # full-sample macro betas
    long_daily: pd.DataFrame                # all cached history (2000 on), for the analog engine
    backtests: dict[int, pd.DataFrame]      # horizon (weeks) -> walk-forward analog backtest


class MissingCache(Exception):
    pass


def sync_published() -> bool:
    """Download the CSVs listed in the data branch's manifest into the cache.

    Returns False (leaving the cache untouched) if the published data can't
    be reached, e.g. before the refresh-data workflow has first run.
    """
    try:
        resp = requests.get(f"{PUBLISHED_DATA_URL}/manifest.json", headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        files = resp.json()["files"]
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for name in files:
            if not name.endswith(".csv") or "/" in name or "\\" in name:
                continue  # manifest is remote input: only plain CSV names in the cache dir
            r = requests.get(f"{PUBLISHED_DATA_URL}/{name}", headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            (CACHE_DIR / name).write_bytes(r.content)
        return True
    except (requests.RequestException, KeyError, ValueError):
        return False


def load() -> DashboardData:
    if DATA_SOURCE == "published" or cache.load("prices") is None:
        sync_published()
    if cache.load("prices") is None:
        raise MissingCache("python -m slv_dashboard.refresh")
    long_daily = dataset.build(start=None)
    daily = long_daily[long_daily.index >= HISTORY_START]
    betas, rule = {}, {}
    for w in REGRESSION_WINDOWS_WEEKS:
        b, r = cache.load(f"betas_macro_{w}w"), cache.load(f"regime_rule_{w}w")
        if b is None or r is None:
            raise MissingCache("python -m slv_dashboard.models.report")
        betas[w], rule[w] = b, r
    full = drivers.full_sample(drivers.weekly_returns(daily), drivers.MACRO).params.drop("const")
    backtests = {h: bt for h in (4, 13) if (bt := cache.load(f"analog_backtest_{h}w")) is not None and not bt.empty}
    return DashboardData(daily, betas, rule, cache.load("regime_markov"), full, long_daily, backtests)


def clip(obj, range_key: str):
    """Slice a frame or series to the selected trailing range."""
    years = RANGES[range_key]
    if years is None or obj is None or obj.empty:
        return obj
    return obj[obj.index >= obj.index.max() - pd.DateOffset(years=years)]


def change(s: pd.Series, periods: int) -> float | None:
    s = s.dropna()
    if len(s) <= periods:
        return None
    return float(s.iloc[-1] - s.iloc[-1 - periods])


def percentile(s: pd.Series) -> float | None:
    """Where the latest value sits in the series' own history (0-1)."""
    s = s.dropna()
    if s.empty:
        return None
    return float((s <= s.iloc[-1]).mean())


def what_changed(s: pd.Series, fmt: str = ",.2f", unit: str = "", periods: int = 5) -> str:
    """One-line 'what changed this week' caption: level, 1-week change, percentile."""
    s = s.dropna()
    if s.empty:
        return ""
    chg = change(s, periods)
    pct = percentile(s)
    parts = [f"Now {s.iloc[-1]:{fmt}}{unit}"]
    if chg is not None:
        parts.append(f"{chg:+{fmt}}{unit} this week")
    if pct is not None:
        parts.append(f"{pct:.0%} percentile since {s.index[0]:%Y}")
    return " · ".join(parts)


# Rows of the weekly "what changed" table: column, label, number format, unit
WEEKLY_ROWS = [
    ("silver", "Silver ($/oz)", ",.2f", ""),
    ("gold", "Gold ($/oz)", ",.0f", ""),
    ("gold_silver_ratio", "Gold/silver ratio", ".1f", ""),
    ("copper", "Copper ($/lb)", ",.3f", ""),
    ("real_yield_10y", "10Y real yield", ".2f", "%"),
    ("nominal_2y", "2Y Treasury", ".2f", "%"),
    ("breakeven_10y", "10Y breakeven", ".2f", "%"),
    ("dollar_broad", "Broad dollar", ".1f", ""),
    ("vix", "VIX", ".1f", ""),
    ("mm_net_pct_oi", "Managed money net (% OI)", ".1f", ""),
    ("slv_ounces", "SLV ounces (M)", ",.1f", ""),
]


def weekly_table(daily: pd.DataFrame) -> pd.DataFrame:
    """Level, 1-week and 4-week change, and percentile for each tracked series."""
    rows = []
    for col, label, fmt, unit in WEEKLY_ROWS:
        if col not in daily or daily[col].dropna().empty:
            continue
        s = daily[col].dropna()
        if col == "slv_ounces":
            s = s / 1e6
        if col == "mm_net_pct_oi":
            s = s[s.ne(s.shift())]  # one value per COT release
            w1, w4 = change(s, 1), change(s, 4)
        else:
            w1, w4 = change(s, 5), change(s, 20)
        rows.append({"Series": label, "Latest": f"{s.iloc[-1]:{fmt}}{unit}",
                     "1w change": "" if w1 is None else f"{w1:+{fmt}}",
                     "4w change": "" if w4 is None else f"{w4:+{fmt}}",
                     "Percentile": "" if (pc := percentile(s)) is None else f"{pc:.0%}",
                     "As of": f"{s.index[-1]:%b %d}"})
    return pd.DataFrame(rows).set_index("Series")
