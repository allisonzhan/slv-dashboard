"""Series definitions and project settings."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"

load_dotenv(ROOT / ".env")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Futures prices from yfinance
PRICE_TICKERS = {
    "silver": "SI=F",
    "gold": "GC=F",
    "copper": "HG=F",
}

# Macro series from FRED
FRED_SERIES = {
    "real_yield_10y": "DFII10",   # 10Y TIPS yield, %
    "dollar_broad": "DTWEXBGS",   # Broad trade-weighted dollar index
}

# Rolling windows (trading days) for the driver regressions
REGRESSION_WINDOWS = [60, 252]

HISTORY_START = "2010-01-01"
