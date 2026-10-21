"""iShares Silver Trust (SLV) ounces in trust.

The product page only shows today's figure, so history builds up in the
cache one row per refresh. Run the refresh daily to grow it.
"""

import re
from datetime import datetime

import pandas as pd
import requests

from slv_dashboard.config import HTTP_TIMEOUT, SLV_PRODUCT_URL
from slv_dashboard.data import cache

NAME = "etf_holdings"

# Embedded JSON on the page: "ounces":{..."formattedValue":"497,650,755.40",..."formattedAsOfDate":"Oct 19, 2026"
_OUNCES_RE = re.compile(
    r'"ounces":\{[^}]*?"formattedValue":"(?P<value>[\d,.]+)"[^}]*?"formattedAsOfDate":"(?P<date>[A-Za-z]{3} \d{1,2}, \d{4})"'
)


def parse(html: str) -> pd.DataFrame:
    html = html.replace("&quot;", '"')
    m = _OUNCES_RE.search(html)
    if not m:
        raise ValueError("Ounces in Trust not found on the SLV page; the page layout may have changed")
    date = datetime.strptime(m["date"], "%b %d, %Y")
    ounces = float(m["value"].replace(",", ""))
    return pd.DataFrame({"slv_ounces": [ounces]}, index=pd.DatetimeIndex([date], name="date"))


def fetch() -> pd.DataFrame:
    # iShares serves the page to browser-style user agents only
    resp = requests.get(SLV_PRODUCT_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return parse(resp.text)


def refresh() -> pd.DataFrame:
    return cache.append(NAME, fetch())
