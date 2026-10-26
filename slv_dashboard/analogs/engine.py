"""Find past weeks that looked like a query week and summarise what happened next.

Matching combines two views a trader uses:
- state distance: weighted Euclidean distance on the feature vector,
  standardised against the candidate pool (only weeks before the query), with
  each feature group weighted equally so 9 technical features don't drown out
  2 positioning ones;
- path shape: correlation of the last ANALOG_SHAPE_DAYS of normalised log
  price, i.e. "the chart looks like this".

Rules that keep the read honest:
- a candidate's whole forward window must end before the query date, so no
  analog's outcome overlaps today;
- analogs are de-clustered (one per ANALOG_MIN_GAP_WEEKS), so a long episode
  like 2011 can't fill the list with near-duplicate weeks;
- every statistic is shown next to the unconditional base rate over the same
  history, and the edge gets a bootstrap p-value.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from slv_dashboard.analogs import features as feat
from slv_dashboard.config import (ANALOG_HORIZONS_WEEKS, ANALOG_K, ANALOG_MIN_GAP_WEEKS, ANALOG_SHAPE_DAYS,
                                  ANALOG_SHAPE_WEIGHT)

BOOTSTRAP_DRAWS = 2000
MIN_CANDIDATES = 52

# Labelled episodes so an analog date reads as a story in a pitch. Broad
# windows on purpose; anything not listed just shows its numbers.
EPISODES = [
    ("2006-04-01", "2006-06-30", "SLV launch spike and May 2006 flush"),
    ("2008-03-01", "2008-03-31", "Bear Stearns peak"),
    ("2008-08-01", "2008-12-31", "GFC deleveraging"),
    ("2009-01-01", "2009-12-31", "Post-GFC QE1 recovery"),
    ("2010-08-01", "2011-04-30", "QE2 rally to $49"),
    ("2011-05-01", "2011-12-31", "2011 blow-off top and margin hikes"),
    ("2013-04-01", "2013-06-30", "April 2013 crash / taper tantrum"),
    ("2013-07-01", "2015-12-31", "Post-QE bear market"),
    ("2016-01-01", "2016-08-31", "2016 rebound (Fed pause, Brexit)"),
    ("2018-04-01", "2018-12-31", "Strong-dollar 2018 lows"),
    ("2019-06-01", "2019-09-30", "2019 Fed cuts breakout"),
    ("2020-03-01", "2020-03-31", "COVID liquidation"),
    ("2020-04-01", "2020-08-31", "COVID reflation rally"),
    ("2021-01-15", "2021-02-28", "#silversqueeze"),
    ("2022-03-01", "2022-10-31", "2022 Fed hiking cycle"),
    ("2024-02-15", "2024-05-31", "2024 breakout (gold record highs)"),
    ("2025-09-01", "2025-11-30", "Oct 2025 London liquidity squeeze"),
    ("2026-01-15", "2026-02-28", "Jan 2026 blow-off and crash"),
]


def episode(date: pd.Timestamp) -> str:
    for start, end, label in EPISODES:
        if pd.Timestamp(start) <= date <= pd.Timestamp(end):
            return label
    return ""


class AnalogContext:
    """Precomputed forward outcomes and path shapes for one target.

    Built once (cheap), then queried many times: the dashboard queries the
    latest week, the backtest queries every week since 2010.
    """

    def __init__(self, daily_price: pd.Series, weekly: pd.DataFrame,
                 horizons: list[int] = ANALOG_HORIZONS_WEEKS, shape_days: int = ANALOG_SHAPE_DAYS):
        self.price = daily_price.dropna()
        self.weekly = weekly.loc[weekly.index.isin(self.price.index)]
        self.horizons = horizons
        self.shape_days = shape_days
        self.pos = self.price.index.get_indexer(self.weekly.index)
        px = self.price.to_numpy()
        n = len(self.weekly)

        # Forward outcomes from each weekly row to the row h weeks later
        self.outcomes = {}
        for h in horizons:
            fwd, mae, mfe, vol = (np.full(n, np.nan) for _ in range(4))
            for i in range(n - h):
                a, b = self.pos[i], self.pos[i + h]
                window = px[a:b + 1]
                fwd[i] = window[-1] / window[0] - 1
                mae[i] = window[1:].min() / window[0] - 1
                mfe[i] = window[1:].max() / window[0] - 1
                vol[i] = np.diff(np.log(window)).std(ddof=1) * np.sqrt(252) if len(window) > 2 else np.nan
            self.outcomes[h] = pd.DataFrame({"fwd": fwd, "mae": mae, "mfe": mfe, "fwd_vol": vol},
                                            index=self.weekly.index)

        # Normalised trailing log-price path per weekly row, for shape correlation
        logp = np.log(px)
        self.shapes = np.full((n, shape_days), np.nan)
        for i, a in enumerate(self.pos):
            if a + 1 >= shape_days:
                seg = logp[a + 1 - shape_days:a + 1]
                sd = seg.std()
                if sd > 0:
                    self.shapes[i] = (seg - seg.mean()) / sd

    @classmethod
    def from_daily(cls, daily: pd.DataFrame, target: str = "silver", **kw) -> "AnalogContext":
        return cls(feat.target_series(daily, target), feat.build(daily, target), **kw)

    def path(self, i: int, days: int) -> np.ndarray:
        """Cumulative simple return over the next ``days`` trading days from weekly row i."""
        a = self.pos[i]
        seg = self.price.to_numpy()[a:a + days + 1]
        out = np.full(days + 1, np.nan)
        out[:len(seg)] = seg / seg[0] - 1
        return out


@dataclass
class AnalogResult:
    query_date: pd.Timestamp
    matches: pd.DataFrame          # one row per analog: score parts, features, forward outcomes
    outcomes: pd.DataFrame         # one row per horizon: conditional vs. base-rate stats
    paths: pd.DataFrame            # trading days ahead x analog date, cumulative return
    features_used: list[str]
    n_candidates: int
    query_features: pd.Series = field(default_factory=pd.Series)


def _standardise(pool: pd.DataFrame, query: pd.Series):
    mu, sd = pool.mean(), pool.std().replace(0, np.nan)
    return (pool - mu) / sd, (query - mu) / sd


def _weights(cols: list[str]) -> pd.Series:
    """Equal weight per feature group, split evenly inside each group."""
    w = {}
    for group in feat.GROUPS.values():
        present = [c for c in group if c in cols]
        for c in present:
            w[c] = 1 / len(present)
    return pd.Series(w)[cols]


def _decluster(order: pd.Index, gap_weeks: int, k: int) -> list[pd.Timestamp]:
    picked: list[pd.Timestamp] = []
    gap = pd.Timedelta(weeks=gap_weeks)
    for d in order:
        if all(abs(d - p) >= gap for p in picked):
            picked.append(d)
            if len(picked) == k:
                break
    return picked


def summarise(fwd: pd.DataFrame, base: pd.DataFrame, rng: np.random.Generator | None = None) -> dict:
    """Conditional outcome stats for one horizon next to the base rate.

    ``fwd`` and ``base`` have columns fwd/mae/mfe/fwd_vol; ``base`` is every
    eligible week over the same history. The p-value is two-sided: how often
    a random set of the same size has a median at least as far from the base
    median as the analogs do.
    """
    rng = rng or np.random.default_rng(0)
    r, b = fwd["fwd"].dropna(), base["fwd"].dropna()
    n = len(r)
    if n == 0 or len(b) == 0:
        return {"n": n}
    med, base_med = float(r.median()), float(b.median())
    draws = rng.choice(b.to_numpy(), size=(BOOTSTRAP_DRAWS, n), replace=True)
    p = float((np.abs(np.median(draws, axis=1) - base_med) >= abs(med - base_med)).mean())
    return {
        "n": n,
        "hit_rate": float((r > 0).mean()),
        "mean": float(r.mean()),
        "median": med,
        "q25": float(r.quantile(0.25)),
        "q75": float(r.quantile(0.75)),
        "mae_median": float(fwd["mae"].median()),
        "mae_q25": float(fwd["mae"].quantile(0.25)),
        "mfe_median": float(fwd["mfe"].median()),
        "mfe_q75": float(fwd["mfe"].quantile(0.75)),
        "fwd_vol_median": float(fwd["fwd_vol"].median()),
        "base_hit_rate": float((b > 0).mean()),
        "base_median": base_med,
        "base_fwd_vol_median": float(base["fwd_vol"].median()),
        "edge_median": med - base_med,
        "edge_hit_rate": float((r > 0).mean() - (b > 0).mean()),
        "p_value": p,
    }


def find(ctx: AnalogContext, date: pd.Timestamp | None = None, *, groups=tuple(feat.GROUPS), k: int = ANALOG_K,
         horizon_weeks: int | None = None, min_gap_weeks: int = ANALOG_MIN_GAP_WEEKS,
         shape_weight: float = ANALOG_SHAPE_WEIGHT, candidate_filter: pd.Series | None = None,
         with_paths: bool = True, bootstrap: bool = True) -> AnalogResult | None:
    """Top-k de-clustered analogs for the weekly row at (or just before) ``date``.

    ``horizon_weeks`` (default: the longest horizon) sets how far forward each
    candidate's outcome must be fully known before the query. Features that
    are missing at the query date are dropped; candidates missing any of the
    remaining features are skipped. ``candidate_filter`` (bool Series on
    weekly dates) restricts the pool, e.g. to the same regime.
    """
    w = ctx.weekly
    horizon_weeks = horizon_weeks or max(ctx.horizons)
    qi = len(w) - 1 if date is None else int(w.index.searchsorted(pd.Timestamp(date), side="right")) - 1
    if qi < 0:
        return None
    qdate = w.index[qi]
    cols = [c for g in groups for c in feat.GROUPS[g] if c in w and pd.notna(w[c].iloc[qi])]
    if not cols and shape_weight <= 0:
        return None

    pool_idx = w.index[:max(qi - horizon_weeks + 1, 0)]
    pool = w.loc[pool_idx, cols].dropna() if cols else w.loc[pool_idx, []]
    if candidate_filter is not None:
        keep = candidate_filter.reindex(pool.index).fillna(False).astype(bool)
        pool = pool[keep]
    if len(pool) < MIN_CANDIDATES:
        return None

    score = pd.Series(0.0, index=pool.index)
    dist = pd.Series(np.nan, index=pool.index)
    if cols:
        zp, zq = _standardise(pool, w[cols].iloc[qi])
        wts = _weights(cols)
        dist = np.sqrt(((zp - zq) ** 2 * wts).sum(axis=1) / wts.sum())
        score += (1 - shape_weight) * dist / dist.median()
    rows = w.index.get_indexer(pool.index)
    qshape = ctx.shapes[qi]
    corr = pd.Series(ctx.shapes[rows] @ qshape / ctx.shape_days, index=pool.index)
    if shape_weight > 0 and not np.isnan(qshape).any():
        score += shape_weight * (1 - corr.fillna(-1))
    order = score.sort_values().index
    picked = _decluster(order, min_gap_weeks, k)

    matches = pd.DataFrame({"score": score[picked], "distance": dist[picked], "shape_corr": corr[picked]})
    matches["episode"] = [episode(d) for d in picked]
    matches = matches.join(w.loc[picked, cols])
    for h in ctx.horizons:
        if h > horizon_weeks:
            continue
        o = ctx.outcomes[h].loc[picked]
        matches[f"fwd_{h}w"] = o["fwd"]
        matches[f"mae_{h}w"] = o["mae"]
        matches[f"mfe_{h}w"] = o["mfe"]

    rng = np.random.default_rng(0)
    stats = {}
    for h in ctx.horizons:
        if h > horizon_weeks:
            continue
        # Base rate: every week from the start of the candidate pool whose
        # h-week outcome is known by the query date
        base = ctx.outcomes[h].iloc[:max(qi - h + 1, 0)]
        base = base[base.index >= pool.index.min()]
        s = summarise(ctx.outcomes[h].loc[picked], base, rng) if bootstrap else summarise_fast(
            ctx.outcomes[h].loc[picked], base)
        stats[h] = s
    outcomes = pd.DataFrame(stats).T
    outcomes.index.name = "horizon_weeks"

    paths = pd.DataFrame()
    if with_paths:
        days = horizon_weeks * 5
        paths = pd.DataFrame({d: ctx.path(int(r), days) for d, r in zip(picked, w.index.get_indexer(picked))})
        paths.index.name = "days_ahead"
    return AnalogResult(qdate, matches, outcomes, paths, cols, len(pool), w[cols].iloc[qi])


def summarise_fast(fwd: pd.DataFrame, base: pd.DataFrame) -> dict:
    """Median and hit rate only (used by the walk-forward backtest)."""
    r, b = fwd["fwd"].dropna(), base["fwd"].dropna()
    if len(r) == 0 or len(b) == 0:
        return {"n": len(r)}
    return {"n": len(r), "hit_rate": float((r > 0).mean()), "median": float(r.median()),
            "base_hit_rate": float((b > 0).mean()), "base_median": float(b.median()),
            "edge_median": float(r.median() - b.median())}


def describe(row: pd.Series) -> str:
    """One-line context for an analog, e.g. for the analog table or a pitch."""
    parts = []
    fmt = {
        "ret_13w": lambda v: f"13w {v:+.0%}",
        "rsi14": lambda v: f"RSI {v:.0f}",
        "ry_chg_13w": lambda v: f"real yld {v * 100:+.0f}bp/13w",
        "usd_ret_13w": lambda v: f"USD {v:+.1%}/13w",
        "gsr_z": lambda v: f"GSR z {v:+.1f}",
        "mm_pctile": lambda v: f"MM {v:.0%} pctile",
    }
    for col, f in fmt.items():
        if col in row and pd.notna(row[col]):
            parts.append(f(row[col]))
    return ", ".join(parts)
