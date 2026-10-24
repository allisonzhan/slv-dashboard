"""Load cached data and model outputs for the dashboard."""

from dataclasses import dataclass

import pandas as pd
import requests

from slv_dashboard.config import (CACHE_DIR, DATA_SOURCE, HTTP_HEADERS, HTTP_TIMEOUT, PUBLISHED_DATA_URL,
                                  REGRESSION_WINDOWS_WEEKS)
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
    daily = dataset.build()
    betas, rule = {}, {}
    for w in REGRESSION_WINDOWS_WEEKS:
        b, r = cache.load(f"betas_macro_{w}w"), cache.load(f"regime_rule_{w}w")
        if b is None or r is None:
            raise MissingCache("python -m slv_dashboard.models.report")
        betas[w], rule[w] = b, r
    full = drivers.full_sample(drivers.weekly_returns(daily), drivers.MACRO).params.drop("const")
    return DashboardData(daily, betas, rule, cache.load("regime_markov"), full)


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
