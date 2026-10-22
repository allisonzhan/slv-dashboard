"""CFTC Commitments of Traders (disaggregated, futures only) for COMEX silver."""

import pandas as pd
import requests

from slv_dashboard.config import CFTC_DISAGG_URL, CFTC_SILVER_CODE, HISTORY_START, HTTP_HEADERS, HTTP_TIMEOUT
from slv_dashboard.data import cache

NAME = "cot"

# Positions are as of Tuesday but published Friday afternoon; joining on the
# Tuesday date would leak information the market didn't have yet
RELEASE_LAG = pd.Timedelta(days=3)

# API field -> our column name
FIELDS = {
    "open_interest_all": "open_interest",
    "m_money_positions_long_all": "mm_long",
    "m_money_positions_short_all": "mm_short",
    "prod_merc_positions_long": "producer_long",
    "prod_merc_positions_short": "producer_short",
    "swap_positions_long_all": "swap_long",
    "swap__positions_short_all": "swap_short",
}


def fetch(start: str = HISTORY_START) -> pd.DataFrame:
    params = {
        "cftc_contract_market_code": CFTC_SILVER_CODE,
        "$where": f"report_date_as_yyyy_mm_dd >= '{start}T00:00:00'",
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": 5000,
    }
    resp = requests.get(CFTC_DISAGG_URL, params=params, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return parse(resp.json())


def parse(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    out = df[list(FIELDS)].apply(pd.to_numeric).rename(columns=FIELDS)
    out.index = pd.to_datetime(df["report_date_as_yyyy_mm_dd"])
    out.index.name = "date"
    out["mm_net"] = out["mm_long"] - out["mm_short"]
    out["mm_net_pct_oi"] = out["mm_net"] / out["open_interest"] * 100
    return out.sort_index()


def refresh() -> pd.DataFrame:
    df = fetch()
    cache.save(NAME, df)
    return df
