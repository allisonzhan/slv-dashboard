"""Named setups: rules a trader would say out loud, with their historical record.

Each setup is a boolean rule on the weekly feature frame. The event study
takes the first week of each episode (triggers within ANALOG_MIN_GAP_WEEKS of
an earlier one are the same episode), and reports forward outcomes against
the base rate, exactly like the analog engine.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from slv_dashboard import catalysts
from slv_dashboard.analogs import engine
from slv_dashboard.config import ANALOG_MIN_GAP_WEEKS


@dataclass(frozen=True)
class Setup:
    key: str
    name: str
    description: str
    rule: Callable[[pd.DataFrame], pd.Series]
    view: str            # what the setup is usually read as: bullish / bearish / volatility


def _gsr_high_turning(w):
    return (w["gsr"] > 85) & (w["gsr"].diff(4) < 0)


SETUPS = [
    Setup("gsr_high_turning", "Gold/silver ratio above 85 and rolling over",
          "Silver historically cheap vs. gold and starting to catch up", _gsr_high_turning, "bullish"),
    Setup("crowded_short", "Managed money in bottom 10% of history",
          "Specs are as short as they get: short-covering fuel", lambda w: w["mm_pctile"] < 0.10, "bullish"),
    Setup("crowded_long", "Managed money in top 10% of history",
          "Specs are as long as they get: liquidation risk", lambda w: w["mm_pctile"] > 0.90, "bearish"),
    Setup("oversold_falling_yields", "RSI below 30 while real yields fall",
          "Price washed out while the main macro driver turns supportive",
          lambda w: (w["rsi14"] < 30) & (w["ry_chg_13w"] < 0), "bullish"),
    Setup("breakout_room_to_run", "52-week high with positioning below median",
          "New highs before the specs have piled in", lambda w: w["breakout_52w"] & (w["mm_pctile"] < 0.5),
          "bullish"),
    Setup("golden_cross", "Golden cross (50d above 200d)", "Classic trend-change signal",
          lambda w: w["golden_cross"], "bullish"),
    Setup("death_cross", "Death cross (50d below 200d)", "Classic trend-change signal",
          lambda w: w["death_cross"], "bearish"),
    Setup("vol_extreme", "20-day volatility in top 10% of history",
          "Blow-off or flush: forward ranges are wide", lambda w: w["vol_pctile"] > 0.90, "volatility"),
    Setup("deep_drawdown", "25%+ below the 52-week high", "Bear-market territory",
          lambda w: w["dd_52w"] < -0.25, "bullish"),
    Setup("overextended", "Up 30%+ in 13 weeks with RSI above 70", "Parabolic move, prone to sharp pullbacks",
          lambda w: (w["ret_13w"] > 0.30) & (w["rsi14"] > 70), "bearish"),
    Setup("fomc_week", "FOMC decision week (2019 on)", "How silver has traded from the week of a Fed decision",
          lambda w: catalysts.fomc_week_mask(w.index), "event"),
]


def triggers(mask: pd.Series, min_gap_weeks: int = ANALOG_MIN_GAP_WEEKS) -> pd.DatetimeIndex:
    """First week of each episode where ``mask`` is true."""
    hits = mask.fillna(False).astype(bool)
    hits = hits[hits].index
    out, last = [], None
    for d in hits:
        if last is None or d - last >= pd.Timedelta(weeks=min_gap_weeks):
            out.append(d)
        last = d   # an unbroken run of triggers stays one episode
    return pd.DatetimeIndex(out)


def study(ctx: engine.AnalogContext, mask: pd.Series, min_gap_weeks: int = ANALOG_MIN_GAP_WEEKS) -> dict:
    """Event-study stats per horizon for trigger dates whose outcome is known."""
    dates = triggers(mask.reindex(ctx.weekly.index), min_gap_weeks)
    rng = np.random.default_rng(0)
    first = dates.min() if len(dates) else ctx.weekly.index[0]
    stats = {}
    for h in ctx.horizons:
        o = ctx.outcomes[h]
        base = o[o.index >= first]
        stats[h] = engine.summarise(o.loc[dates], base, rng)
    return {"dates": dates, "stats": pd.DataFrame(stats).T}


def scan(ctx: engine.AnalogContext, setups: list[Setup] = SETUPS, live_weeks: int = 1) -> pd.DataFrame:
    """One row per setup per horizon, with whether it's live (fired in the last ``live_weeks``)."""
    w = ctx.weekly
    rows = []
    for s in setups:
        try:
            mask = s.rule(w).fillna(False).astype(bool)
        except KeyError:  # feature not available for this target
            continue
        res = study(ctx, mask)
        live = bool(mask.iloc[-live_weeks:].any())
        last = res["dates"].max() if len(res["dates"]) else pd.NaT
        for h, st in res["stats"].iterrows():
            rows.append({"key": s.key, "setup": s.name, "description": s.description, "view": s.view,
                         "live": live, "last_trigger": last, "horizon_weeks": int(h), **st.to_dict()})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["live", "key", "horizon_weeks"], ascending=[False, True, True]).reset_index(drop=True)
