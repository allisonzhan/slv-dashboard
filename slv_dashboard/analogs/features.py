"""Weekly state vector for analog matching, built with no look-ahead.

Every feature at week t uses only data up to t: rolling windows look back,
and percentiles are expanding ranks. Truncating the input after t leaves the
row for t unchanged (tested). Raw values are returned; the engine
standardises them against the candidate pool at query time.

Rows are the last trading day of each week (not the Friday label), so a run
mid-week matches today's state rather than last Friday's.
"""

import numpy as np
import pandas as pd

from slv_dashboard import instruments
from slv_dashboard.models import channels

# What a trader would want to compare: the tradable instruments (ETFs and
# futures, see slv_dashboard/instruments.py), plus ratios and spreads so the
# same engine covers relative-value trades.
RATIOS = {
    "gsr": "Gold/silver ratio",
    "slv_sil": "SLV / SIL (metal vs. miners)",
    "silver_copper": "Silver / copper",
}
TARGETS = {k: inst.label for k, inst in instruments.INSTRUMENTS.items()} | RATIOS

GROUPS = {
    "technical": ["ma50_z", "ma200_z", "ret_4w", "ret_13w", "ret_26w", "rsi14", "bb_pctb", "dd_52w", "vol_pctile"],
    "macro": ["ry_chg_13w", "usd_ret_13w", "gold_ret_13w", "gsr_z", "copper_ret_13w"],
    "positioning": ["mm_pctile", "mm_chg_4w"],
    # News backdrop: geopolitical risk (GPR index), the oil shock and market stress
    "events": ["gpr_pctile", "gpr_chg_4w", "oil_ret_4w", "vix_pctile"],
}

LABELS = {
    "ma50_z": "Distance from 50d MA (daily σ)",
    "ma200_z": "Distance from 200d MA (daily σ)",
    "ret_4w": "4-week return",
    "ret_13w": "13-week return",
    "ret_26w": "26-week return",
    "rsi14": "RSI(14)",
    "bb_pctb": "Bollinger %b",
    "dd_52w": "Drawdown from 52w high",
    "vol_pctile": "20d vol percentile",
    "ry_chg_13w": "Real yield 13w change (pp)",
    "usd_ret_13w": "Dollar 13w return",
    "gold_ret_13w": "Gold 13w return",
    "gsr_z": "Gold/silver ratio z (3y)",
    "copper_ret_13w": "Copper 13w return",
    "mm_pctile": "Managed money net % OI percentile",
    "mm_chg_4w": "Managed money 4w change (pts of OI)",
    "gpr_pctile": "Geopolitical risk (4w avg) percentile",
    "gpr_chg_4w": "Geopolitical risk 4w change (log)",
    "oil_ret_4w": "Oil 4w return",
    "vix_pctile": "VIX percentile",
}

MIN_PCTILE_WEEKS = 52   # expanding percentiles start after a year of history
GSR_Z_WEEKS = 156


def target_series(daily: pd.DataFrame, target: str) -> pd.Series:
    """Daily price (or ratio) series for a target key in TARGETS.

    ETFs are back-extended with futures returns before launch (instruments.price).
    """
    if target in instruments.INSTRUMENTS:
        s = instruments.price(daily, target)
    elif target == "gsr":
        s = daily["gold"] / daily["silver"]
    elif target == "slv_sil":
        s = daily["slv"] / daily["sil"] if {"slv", "sil"} <= set(daily.columns) else pd.Series(dtype=float)
    elif target == "silver_copper":
        s = daily["silver"] / daily["copper"]
    else:
        raise KeyError(f"Unknown target {target!r}; choose from {list(TARGETS)}")
    return s.dropna().rename(target)


def metal_of(target: str) -> str:
    """Which metal's positioning and setups apply; ratios are read from silver's side."""
    return instruments.INSTRUMENTS[target].metal if target in instruments.INSTRUMENTS else "silver"


def rsi(p: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI."""
    d = p.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / down)


def technicals(p: pd.Series) -> pd.DataFrame:
    """Daily technical indicators on one price series (also used for the price chart)."""
    lr = np.log(p).diff()
    sigma = lr.rolling(20).std()                        # daily vol, used to scale MA distance
    sma20, sma50, sma200 = (p.rolling(n).mean() for n in (20, 50, 200))
    sd20 = p.rolling(20).std()
    hi252 = p.rolling(252, min_periods=200).max()
    return pd.DataFrame({
        "price": p,
        "sma20": sma20, "sma50": sma50, "sma200": sma200,
        "bb_upper": sma20 + 2 * sd20, "bb_lower": sma20 - 2 * sd20,
        "ma50_z": np.log(p / sma50) / sigma,
        "ma200_z": np.log(p / sma200) / sigma,
        "ret_4w": p.pct_change(20),
        "ret_13w": p.pct_change(65),
        "ret_26w": p.pct_change(130),
        "rsi14": rsi(p),
        "bb_pctb": (p - (sma20 - 2 * sd20)) / (4 * sd20),
        "dd_52w": p / hi252 - 1,
        "vol20": sigma * np.sqrt(252),
        "breakout_52w": p >= hi252,
        "golden_cross": (sma50 > sma200) & (sma50.shift() <= sma200.shift()),
        "death_cross": (sma50 < sma200) & (sma50.shift() >= sma200.shift()),
    })


def _week_last_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Last trading day of each Friday-ending week, keeping the actual date."""
    keep = df.groupby(df.index.to_period("W-FRI")).tail(1).index
    return df.loc[keep]


def build(daily: pd.DataFrame, target: str = "silver") -> pd.DataFrame:
    """Weekly feature frame for one target.

    ``daily`` is the aligned frame from ``dataset.build(start=None)``; COT
    columns there are already shifted to their Friday release date.
    Positioning comes from the target's own metal (gold COT for GLD/IAU/GC);
    for gold targets the "gold 13w return" macro feature is left out, since
    it would just repeat the target's own 13-week return.
    """
    metal = metal_of(target)
    p = target_series(daily, target)
    tech = technicals(p)
    d = daily.reindex(p.index)

    def ret_13w(col):
        return d[col].pct_change(65, fill_method=None) if col in d else np.nan

    macro = pd.DataFrame(index=p.index)
    macro["ry_chg_13w"] = d["real_yield_10y"].diff(65) if "real_yield_10y" in d else np.nan
    macro["usd_ret_13w"] = ret_13w("dollar_broad")
    macro["gold_ret_13w"] = ret_13w("gold") if metal != "gold" else np.nan
    macro["copper_ret_13w"] = ret_13w("copper")
    macro["gsr"] = d["gold"] / d["silver"]
    cot_col = "mm_net_pct_oi" if metal == "silver" else "mm_net_pct_oi_gold"
    macro["mm_net_pct_oi"] = d[cot_col] if cot_col in d else np.nan

    # Events backdrop: the GPR index is a daily newspaper count, so it's smoothed over 4 weeks
    if "gpr" in d:
        gpr_4w = d["gpr"].rolling(20, min_periods=10).mean()
        macro["gpr_4w"] = gpr_4w
        macro["gpr_chg_4w"] = np.log(gpr_4w / gpr_4w.shift(20))
    else:
        macro["gpr_4w"] = macro["gpr_chg_4w"] = np.nan
    macro["oil_ret_4w"] = d["oil"].pct_change(20, fill_method=None) if "oil" in d else np.nan
    macro["vix"] = d["vix"] if "vix" in d else np.nan
    ch = channels.classify(d)
    macro = macro.join(ch)

    w = _week_last_rows(tech.join(macro))
    w["vol_pctile"] = w["vol20"].expanding(MIN_PCTILE_WEEKS).rank(pct=True)
    w["gsr_z"] = (w["gsr"] - w["gsr"].rolling(GSR_Z_WEEKS, min_periods=104).mean()) / \
        w["gsr"].rolling(GSR_Z_WEEKS, min_periods=104).std()
    mm = w["mm_net_pct_oi"]
    w["mm_pctile"] = mm.expanding(MIN_PCTILE_WEEKS).rank(pct=True).where(mm.notna())
    w["mm_chg_4w"] = mm.diff(4)
    w["gpr_pctile"] = w["gpr_4w"].expanding(MIN_PCTILE_WEEKS).rank(pct=True).where(w["gpr_4w"].notna())
    w["vix_pctile"] = w["vix"].expanding(MIN_PCTILE_WEEKS).rank(pct=True).where(w["vix"].notna())
    # Events are flagged if they happened on any day of the week, not just the last
    for col in ("breakout_52w", "golden_cross", "death_cross"):
        w[col] = tech[col].groupby(tech.index.to_period("W-FRI")).any().values[-len(w):]
    w.index.name = "date"
    w.attrs["metal"] = metal
    return w


def all_features() -> list[str]:
    return [f for cols in GROUPS.values() for f in cols]
