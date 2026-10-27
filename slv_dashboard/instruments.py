"""Tradable instruments the dashboard can be pointed at.

Each instrument is either a metals ETF or a continuous futures series, tied
to one metal. The metal decides which positioning (CFTC silver vs. gold),
fair-value drivers, setups and futures curve apply.

ETF history is back-extended with the metal's futures returns before the
ETF launched (SLV 2006, GLD 2004, IAU 2005), so the analog engine still has
2000-on history to match against. Prices before ``launch`` are futures
returns scaled to the ETF's first close: right in percent terms, not real
fund prices, and the dashboard says so.
"""

from dataclasses import dataclass

import pandas as pd

from slv_dashboard.config import DEFAULT_INSTRUMENT


@dataclass(frozen=True)
class Instrument:
    key: str            # column in the aligned daily frame
    label: str
    metal: str          # "silver" or "gold"
    kind: str           # "etf" or "futures"
    proxy: str | None   # futures column used to back-extend ETF history
    options: str        # ticker whose option IV is used (futures and IAU borrow the big ETF's)
    unit: str


INSTRUMENTS = {
    "slv": Instrument("slv", "SLV (iShares Silver Trust)", "silver", "etf", "silver", "SLV", "$/share"),
    "silver": Instrument("silver", "Silver futures (SI=F)", "silver", "futures", None, "SLV", "$/oz"),
    "gld": Instrument("gld", "GLD (SPDR Gold Shares)", "gold", "etf", "gold", "GLD", "$/share"),
    "iau": Instrument("iau", "IAU (iShares Gold Trust)", "gold", "etf", "gold", "GLD", "$/share"),
    "gold": Instrument("gold", "Gold futures (GC=F)", "gold", "futures", None, "GLD", "$/oz"),
}

# Ticker shown in trade ideas for each metal's ETF / futures leg
VEHICLES = {"silver": {"etf": "SLV", "futures": "SI"}, "gold": {"etf": "GLD", "futures": "GC"}}


def get(key: str | None = None) -> Instrument:
    return INSTRUMENTS[key or DEFAULT_INSTRUMENT]


def launch(daily: pd.DataFrame, key: str) -> pd.Timestamp | None:
    """First real (not back-extended) price date, or None for futures."""
    inst = get(key)
    if inst.kind != "etf" or key not in daily:
        return None
    return daily[key].first_valid_index()


def price(daily: pd.DataFrame, key: str) -> pd.Series:
    """Daily price series, with ETF history back-extended by futures returns before launch."""
    inst = get(key)
    own = daily[key].dropna() if key in daily else pd.Series(dtype=float)
    if inst.proxy is None or inst.proxy not in daily:
        return own.rename(key)
    proxy = daily[inst.proxy].dropna()
    if own.empty:
        return pd.Series(dtype=float, name=key)
    first = own.index[0]
    before = proxy[proxy.index < first]
    if before.empty or first not in proxy.index:
        return own.rename(key)
    scaled = before * (own.iloc[0] / proxy.loc[first])
    return pd.concat([scaled, own]).rename(key)
