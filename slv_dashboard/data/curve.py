"""COMEX silver futures curve: front-to-next spread and the implied lease rate.

Silver normally trades in contango: a later contract costs more than the
front by roughly the cost of financing the metal. When the spread is
narrower than funding (or the curve flips to backwardation), someone is
paying up for metal now: the implied lease rate rises. That is how the
October 2025 London squeeze showed up on screens.

    implied financing  = ln(F2 / F1) / T      (T = years between expiries)
    implied lease rate = funding rate - implied financing

yfinance only lists live contracts, so history builds up from each refresh
(plus a short backfill of the current two contracts' shared history).
"""

import calendar
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

from slv_dashboard.data import cache

NAME = "curve"

# Liquid silver delivery months on COMEX, by month number. January (F) is
# listed but thin, and its prices make the front-next spread noisy.
MONTH_CODES = {3: "H", 5: "K", 7: "N", 9: "U", 12: "Z"}
N_CONTRACTS = 4
BACKFILL_PERIOD = "6mo"


def expiry(year: int, month: int) -> date:
    """Approximate last trading day: third-last business day of the contract month."""
    last = date(year, month, calendar.monthrange(year, month)[1])
    days = pd.bdate_range(date(year, month, 1), last)
    return days[-3].date()


def next_contracts(today: date, n: int = N_CONTRACTS) -> list[tuple[str, date]]:
    """Yahoo tickers and approximate expiries for the next ``n`` active contracts.

    A contract is skipped once it's within its delivery month, when most open
    interest has already rolled to the next one.
    """
    out, y, m = [], today.year, today.month
    while len(out) < n:
        if m in MONTH_CODES and (y, m) > (today.year, today.month):
            out.append((f"SI{MONTH_CODES[m]}{y % 100:02d}.CMX", expiry(y, m)))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def spread_metrics(f1: float, f2: float, exp1: date, exp2: date, funding_pct: float | None) -> dict:
    t = (exp2 - exp1).days / 365.25
    financing = np.log(f2 / f1) / t * 100
    return {
        "front": f1, "next": f2,
        "spread": f2 - f1,
        "implied_financing_pct": financing,
        "implied_lease_pct": (funding_pct - financing) if funding_pct is not None else np.nan,
        "backwardation": f2 < f1,
    }


def _funding_rate() -> float | None:
    macro = cache.load("macro")
    if macro is None or "fed_funds" not in macro:
        return None
    s = macro["fed_funds"].dropna()
    return float(s.iloc[-1]) if len(s) else None


def fetch(today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    contracts = next_contracts(today)
    closes = {}
    for ticker, _ in contracts:
        h = yf.Ticker(ticker).history(period=BACKFILL_PERIOD)["Close"]
        h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
        closes[ticker] = h
    funding = _funding_rate()
    (t1, e1), (t2, e2) = contracts[0], contracts[1]
    both = pd.concat([closes[t1], closes[t2]], axis=1, keys=["f1", "f2"]).dropna()
    rows = {d: spread_metrics(r.f1, r.f2, e1, e2, funding) for d, r in both.iterrows()}
    df = pd.DataFrame.from_dict(rows, orient="index")
    df["front_contract"], df["next_contract"] = t1, t2
    # Latest full curve (one row) for the curve-shape chart
    latest = {f"c{i + 1}": closes[t].iloc[-1] for i, (t, _) in enumerate(contracts) if len(closes[t])}
    for k, v in latest.items():
        df.loc[df.index.max(), k] = v
    for i, (t, e) in enumerate(contracts):
        df.loc[df.index.max(), f"c{i + 1}_expiry"] = e.isoformat()
    df.index.name = "date"
    return df


def refresh() -> pd.DataFrame:
    # Append, so spreads from earlier contract pairs are kept after a roll
    return cache.append(NAME, fetch())
