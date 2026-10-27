"""Align all cached sources into one daily frame for the dashboard and models."""

import numpy as np
import pandas as pd

from slv_dashboard.config import HISTORY_START
from slv_dashboard.data import cache, cftc, comex, etf, fred, gpr, prices


def build(start: str | None = HISTORY_START) -> pd.DataFrame:
    """Daily frame on silver's trading calendar, from ``start`` (None = all cached history).

    Daily macro series are forward-filled over holidays. Weekly COT and
    sparse COMEX/ETF snapshots are forward-filled so each day shows the
    latest known value, never a future one. Forward-filling runs before the
    start cut, so the first rows still carry the latest earlier value.
    """
    px = cache.load(prices.NAME)
    if px is None:
        raise FileNotFoundError("No cached prices; run `python -m slv_dashboard.refresh` first")
    df = px.dropna(subset=["silver"]).copy()

    for name in (fred.NAME, cftc.NAME, cftc.GOLD_NAME, comex.NAME, etf.NAME, gpr.NAME):
        other = cache.load(name)
        if other is None:
            continue
        if name == gpr.NAME:
            other = other.copy()
            other.index = other.index + gpr.PUBLICATION_LAG
        if name in (cftc.NAME, cftc.GOLD_NAME):
            other = other.copy()
            other.index = other.index + cftc.RELEASE_LAG
            if name == cftc.GOLD_NAME:
                other = other.add_suffix("_gold")
        df = df.join(other.reindex(df.index.union(other.index)).ffill().reindex(df.index))

    if start is not None:
        df = df[df.index >= start]
    df["gold_silver_ratio"] = df["gold"] / df["silver"]
    for col in ("silver", "gold", "copper"):
        df[f"{col}_ret"] = np.log(df[col]).diff()
    for col in ("real_yield_10y",):
        if col in df:
            df[f"{col}_chg"] = df[col].diff()
    if "dollar_broad" in df:
        df["dollar_broad_ret"] = np.log(df["dollar_broad"]).diff()
    return df
