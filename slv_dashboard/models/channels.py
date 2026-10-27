"""What kind of shock is the market trading? A transparent, no-look-ahead classifier.

The same headline can push metals either way depending on how it transmits.
A war can bring a safe-haven bid (gold up, yields down) or an inflation
shock (oil up, Fed more hawkish, dollar up, metals down; Hormuz in 2026).
So instead of tagging news as good or bad, this reads the *market's* reaction:
4-week moves in the main cross-asset prices, each scaled by its own history,
combined into one score per channel:

  haven      gold up, real yields down, equities down, VIX up
  inflation  oil up, breakevens up, 2Y up, dollar up
  hawkish    2Y up, real yields up, dollar up, gold down
  dovish     2Y down, real yields down, dollar down, gold up
  risk_off   VIX up, equities down, copper down, oil down
  growth     copper up, equities up, oil up, VIX down

The label is the top-scoring channel when it scores at least LABEL_MIN,
otherwise "quiet". Every scale (z-score denominator) uses only data up to
that week, so a label never depends on the future.
"""

import numpy as np
import pandas as pd

WINDOW = 20             # trading days: about four weeks
MIN_HISTORY = 252       # a year of history before scaling starts
LABEL_MIN = 1.0

# move -> (column, how the move is measured)
MOVES = {
    "gold": ("gold", "logret"),
    "oil": ("oil", "logret"),
    "copper": ("copper", "logret"),
    "spx": ("spx", "logret"),
    "dollar": ("dollar_broad", "logret"),
    "vix": ("vix", "logret"),
    "real_yield": ("real_yield_10y", "diff"),
    "nominal_2y": ("nominal_2y", "diff"),
    "breakeven": ("breakeven_10y", "diff"),
}

# channel -> {move: weight}; scores are weighted means of the scaled moves
CHANNELS = {
    "haven": {"gold": 1.0, "real_yield": -1.0, "spx": -0.5, "vix": 0.5},
    "inflation": {"oil": 1.0, "breakeven": 1.0, "nominal_2y": 0.5, "dollar": 0.5},
    "hawkish": {"nominal_2y": 1.0, "real_yield": 1.0, "dollar": 1.0, "gold": -0.5},
    "dovish": {"nominal_2y": -1.0, "real_yield": -1.0, "dollar": -1.0, "gold": 0.5},
    "risk_off": {"vix": 1.0, "spx": -1.0, "copper": -0.5, "oil": -0.5},
    "growth": {"copper": 1.0, "spx": 1.0, "oil": 0.5, "vix": -0.5},
}

DESCRIPTIONS = {
    "haven": "Safe-haven bid: gold up while yields and equities fall",
    "inflation": "Inflation shock: oil and breakevens up, Fed and dollar pressure",
    "hawkish": "Hawkish repricing: 2Y and real yields up, dollar up",
    "dovish": "Dovish repricing: yields and dollar down",
    "risk_off": "Risk-off / liquidity: volatility up, equities and commodities down",
    "growth": "Growth / reflation: copper and equities up",
    "quiet": "No dominant shock",
}

# How each channel usually reads for precious metals (prior, before the event studies)
METALS_READ = {"haven": "supportive", "inflation": "mixed to negative (via the Fed and the dollar)",
               "hawkish": "negative", "dovish": "supportive", "risk_off": "negative short term (forced selling)",
               "growth": "supportive for silver via industrial demand", "quiet": "neutral"}


def moves(daily: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """Scaled 4-week moves: each divided by the expanding std of its own history (no look-ahead)."""
    out = {}
    for name, (col, how) in MOVES.items():
        if col not in daily:
            continue
        s = daily[col].astype(float)
        if how == "logret":
            s = s.where(s > 0)
            m = np.log(s).diff(window)
        else:
            m = s.diff(window)
        sd = m.expanding(MIN_HISTORY).std()
        out[name] = m / sd
    return pd.DataFrame(out, index=daily.index)


def classify(daily: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """Daily channel scores, the winning channel (``channel``) and its score."""
    z = moves(daily, window)
    scores = {}
    for ch, weights in CHANNELS.items():
        cols = [m for m in weights if m in z]
        if not cols:
            continue
        w = pd.Series({m: weights[m] for m in cols})
        # Weighted mean over the moves available that day, so missing early series don't zero a channel
        vals = z[cols].mul(w, axis=1)
        avail = z[cols].notna().mul(w.abs(), axis=1).sum(axis=1)
        scores[ch] = vals.sum(axis=1, min_count=1) / avail.replace(0, np.nan)
    out = pd.DataFrame(scores, index=daily.index)
    top = out.fillna(-np.inf).idxmax(axis=1)   # all-NaN rows are masked below
    best = out.max(axis=1, skipna=True)
    out["channel"] = np.where(best >= LABEL_MIN, top, "quiet")
    out.loc[best.isna(), "channel"] = np.nan
    out["channel_score"] = best
    return out
