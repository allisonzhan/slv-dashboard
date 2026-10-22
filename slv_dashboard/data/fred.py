"""Macro series from FRED: 10Y real yield and broad dollar index."""

import io

import pandas as pd
import requests

from slv_dashboard.config import FRED_API_KEY, FRED_SERIES, HISTORY_START, HTTP_HEADERS, HTTP_TIMEOUT
from slv_dashboard.data import cache

NAME = "macro"
KEYLESS_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _fetch_series(series_id: str, start: str) -> pd.Series:
    if FRED_API_KEY:
        from fredapi import Fred

        s = Fred(api_key=FRED_API_KEY).get_series(series_id, observation_start=start)
    else:
        resp = requests.get(KEYLESS_URL, params={"id": series_id}, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        s = parse_keyless_csv(resp.text)
    return s[s.index >= start]


def parse_keyless_csv(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")  # FRED marks gaps with "."
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna()


def fetch(start: str = HISTORY_START) -> pd.DataFrame:
    df = pd.DataFrame({name: _fetch_series(sid, start) for name, sid in FRED_SERIES.items()})
    df.index.name = "date"
    return df


def refresh() -> pd.DataFrame:
    df = fetch()
    cache.save(NAME, df)
    return df
