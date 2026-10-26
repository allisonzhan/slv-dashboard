"""SLV option implied volatility: ATM level and skew, one snapshot per refresh.

yfinance's own impliedVolatility column is unusable outside market hours
(placeholders like 0.00001 or 0.5), so IV is backed out here from the
bid/ask mid with Black-Scholes. The expiry closest to 30 days out is used.

Compare ATM IV with the analogs' forward realised vol: implied above
realised favours selling premium or using spreads; implied below favours
buying options.
"""

from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import brentq
from scipy.stats import norm

from slv_dashboard.data import cache

NAME = "options"
TARGET_DAYS = 30
SKEW_MONEYNESS = 0.10     # compare 10% OTM put vs. 10% OTM call


def bs_price(s: float, k: float, t: float, r: float, vol: float, call: bool) -> float:
    if t <= 0 or vol <= 0:
        return max(0.0, (s - k) if call else (k - s))
    d1 = (np.log(s / k) + (r + vol ** 2 / 2) * t) / (vol * np.sqrt(t))
    d2 = d1 - vol * np.sqrt(t)
    if call:
        return s * norm.cdf(d1) - k * np.exp(-r * t) * norm.cdf(d2)
    return k * np.exp(-r * t) * norm.cdf(-d2) - s * norm.cdf(-d1)


def implied_vol(price: float, s: float, k: float, t: float, r: float, call: bool) -> float:
    """Black-Scholes IV by root-finding; NaN when the price is outside no-arbitrage bounds."""
    intrinsic = max(0.0, (s - k * np.exp(-r * t)) if call else (k * np.exp(-r * t) - s))
    if not np.isfinite(price) or price <= intrinsic + 1e-6:
        return np.nan
    try:
        return brentq(lambda v: bs_price(s, k, t, r, v, call) - price, 1e-4, 5.0)
    except ValueError:
        return np.nan


def _mid(row) -> float:
    if row["bid"] > 0 and row["ask"] > 0:
        return (row["bid"] + row["ask"]) / 2
    return np.nan


def snapshot(spot: float, calls: pd.DataFrame, puts: pd.DataFrame, days: int, r: float) -> dict:
    """ATM IV (mean of the call and put nearest the money), 10% OTM put/call IV and skew."""
    t = days / 365

    def iv_at(chain: pd.DataFrame, strike_target: float, call: bool) -> float:
        chain = chain.assign(dist=(chain["strike"] - strike_target).abs()).sort_values("dist").head(2)
        vals = [implied_vol(_mid(row), spot, row["strike"], t, r, call) for _, row in chain.iterrows()]
        vals = [v for v in vals if np.isfinite(v)]
        return float(np.mean(vals)) if vals else np.nan

    atm = np.nanmean([iv_at(calls, spot, True), iv_at(puts, spot, False)])
    put_iv = iv_at(puts, spot * (1 - SKEW_MONEYNESS), False)
    call_iv = iv_at(calls, spot * (1 + SKEW_MONEYNESS), True)
    return {
        "spot": spot, "days": days,
        "atm_iv": atm, "put_10otm_iv": put_iv, "call_10otm_iv": call_iv,
        "skew_call_minus_put": call_iv - put_iv,
        "expected_move_pct": atm * np.sqrt(t),   # one-sigma move to expiry
    }


def fetch(today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    tk = yf.Ticker("SLV")
    expiries = [date.fromisoformat(e) for e in tk.options]
    exp = min(expiries, key=lambda e: abs((e - today).days - TARGET_DAYS))
    chain = tk.option_chain(exp.isoformat())
    spot = float(tk.history(period="5d")["Close"].iloc[-1])
    macro = cache.load("macro")
    r = float(macro["fed_funds"].dropna().iloc[-1]) / 100 if macro is not None and "fed_funds" in macro else 0.04
    snap = snapshot(spot, chain.calls, chain.puts, max((exp - today).days, 1), r)
    snap["expiry"] = exp.isoformat()
    df = pd.DataFrame([snap], index=pd.DatetimeIndex([pd.Timestamp(today)], name="date"))
    if df[["atm_iv"]].isna().all().all():
        return df.iloc[0:0]   # quotes not live (e.g. weekend): skip rather than store blanks
    return df


def refresh() -> pd.DataFrame:
    new = fetch()
    if new.empty:
        return cache.load(NAME) if cache.load(NAME) is not None else new
    return cache.append(NAME, new)
