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

# Where the dashboard gets its data:
#   "local"     - data/cache/ (falls back to published data if the cache is empty)
#   "published" - always download the CSVs the refresh-data workflow publishes
#                 to the repo's `data` branch (set this on a hosted deployment)
DATA_SOURCE = os.getenv("SLV_DATA_SOURCE", "local")
PUBLISHED_DATA_URL = os.getenv(
    "SLV_PUBLISHED_DATA_URL", "https://raw.githubusercontent.com/allisonzhan/slv-dashboard/data"
)

# Daily closes from yfinance. Futures are continuous front-month series; SLV is
# the clean (roll-free) return series for ETF trades.
PRICE_TICKERS = {
    "silver": "SI=F",
    "gold": "GC=F",
    "copper": "HG=F",
    "slv": "SLV",       # iShares Silver Trust, 2006 on
    "gld": "GLD",       # SPDR Gold Shares, 2004 on
    "iau": "IAU",       # iShares Gold Trust, 2005 on
    "sil": "SIL",       # Global X silver miners, 2010 on
    "vix": "^VIX",
    "oil": "CL=F",
    "spx": "^GSPC",     # S&P 500, for the risk-off / growth shock channels
}

# Instrument the dashboard, brief and trade builder use unless another is picked
# (keys in slv_dashboard/instruments.py: slv, silver, gld, iau, gold)
DEFAULT_INSTRUMENT = "slv"

# Macro series from FRED
FRED_SERIES = {
    "real_yield_10y": "DFII10",   # 10Y TIPS yield, %
    "dollar_broad": "DTWEXBGS",   # Broad trade-weighted dollar index
    "nominal_2y": "DGS2",         # 2Y Treasury yield, % (Fed expectations)
    "breakeven_10y": "T10YIE",    # 10Y breakeven inflation, %
    "fed_funds": "DFF",           # Effective fed funds rate, %
    "fed_target_upper": "DFEDTARU",   # Fed funds target, upper bound (Dec 2008 on): dates Fed moves
    "fed_target_old": "DFEDTAR",      # Fed funds target before Dec 2008
}

# Caldara & Iacoviello geopolitical risk index, daily (1985 on; 1985-2019 = 100).
# Free for research; cite Caldara and Iacoviello (2022), "Measuring Geopolitical
# Risk", American Economic Review. https://www.matteoiacoviello.com/gpr.htm
GPR_DAILY_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"

# CFTC disaggregated futures-only report, COMEX silver and gold
CFTC_DISAGG_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
CFTC_SILVER_CODE = "084691"
CFTC_GOLD_CODE = "088691"

# iShares Silver Trust product page (current ounces in trust)
SLV_PRODUCT_URL = "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund"

# Driver regressions run on weekly (Friday) returns: COMEX settles at 1:30pm ET
# while FRED's yield and dollar series are stamped at other times of day, so
# daily betas would be biased toward zero by the timing mismatch.
REGRESSION_WINDOWS_WEEKS = [26, 52]

# Regime rule: copper's share of explanatory power is ranked against earlier
# windows; this many weeks of windows must exist before labels start.
REGIME_MIN_HISTORY_WEEKS = 104

# Driver models, regimes and the main panels use 2010 on. Loaders pull from
# LONG_HISTORY_START so the analog engine has more past setups to match
# (macro series start later: real yields 2003, broad dollar 2006, COT 2006).
HISTORY_START = "2010-01-01"
LONG_HISTORY_START = "2000-01-01"

# Analog engine (slv_dashboard/analogs)
ANALOG_HORIZONS_WEEKS = [1, 4, 13, 26]
ANALOG_K = 20                 # analogs kept per query
ANALOG_MIN_GAP_WEEKS = 8      # at most one analog per 8-week stretch
ANALOG_SHAPE_DAYS = 60        # trading days of price path compared for shape
ANALOG_SHAPE_WEIGHT = 0.3     # share of the match score from path shape
ANALOG_BACKTEST_START = "2010-01-01"
ANALOG_BACKTEST_INSTRUMENTS = ["slv", "gld"]   # one per metal; others reuse their metal's

HTTP_HEADERS = {"User-Agent": "slv-dashboard (COINS research; github.com/allisonzhan/slv-dashboard)"}
HTTP_TIMEOUT = 60
