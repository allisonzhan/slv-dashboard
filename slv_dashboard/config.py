"""Series definitions and project settings."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
# Files you download by hand (e.g. CME's Silver_stocks.xls) go here
IMPORTS_DIR = ROOT / "data" / "imports"

load_dotenv(ROOT / ".env")
# Optional: FRED's keyless CSV endpoint is used when this is empty
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

# CFTC disaggregated futures-only report, COMEX silver
CFTC_DISAGG_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
CFTC_SILVER_CODE = "084691"

# iShares Silver Trust product page (current ounces in trust)
SLV_PRODUCT_URL = "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund"

# Rolling windows (trading days) for the driver regressions
REGRESSION_WINDOWS = [60, 252]

HISTORY_START = "2010-01-01"

HTTP_HEADERS = {"User-Agent": "slv-dashboard (COINS research; github.com/allisonzhan/slv-dashboard)"}
HTTP_TIMEOUT = 60
