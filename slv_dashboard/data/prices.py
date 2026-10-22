"""Front-month futures closes for silver, gold and copper (yfinance)."""

import pandas as pd
import yfinance as yf

from slv_dashboard.config import HISTORY_START, PRICE_TICKERS
from slv_dashboard.data import cache

NAME = "prices"


def fetch(start: str = HISTORY_START) -> pd.DataFrame:
    raw = yf.download(list(PRICE_TICKERS.values()), start=start, progress=False, auto_adjust=False)
    closes = raw["Close"].rename(columns={v: k for k, v in PRICE_TICKERS.items()})
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    closes.index.name = "date"
    return closes[list(PRICE_TICKERS)].dropna(how="all")


def refresh() -> pd.DataFrame:
    df = fetch()
    cache.save(NAME, df)
    return df
