"""Walk-forward check: would the analog read have helped, out of sample?

Every week from ANALOG_BACKTEST_START, the engine is run as of that week
(candidates and standardisation use only earlier weeks whose outcome was
already known), and its prediction is compared with what actually happened.
This is what separates an edge from a good story: if the analogs' direction
call isn't better than "always bet the base rate", the dashboard says so.

Forward windows of consecutive weeks overlap, so the effective number of
independent observations is roughly n / horizon; treat small differences
as noise.
"""

import numpy as np
import pandas as pd

from slv_dashboard.analogs import engine
from slv_dashboard.config import ANALOG_BACKTEST_START


def run(ctx: engine.AnalogContext, horizon_weeks: int, start: str = ANALOG_BACKTEST_START,
        step_weeks: int = 1, **find_kw) -> pd.DataFrame:
    """One row per query week: analog prediction vs. realised forward return."""
    w = ctx.weekly
    realised = ctx.outcomes[horizon_weeks]["fwd"]
    rows = []
    for d in w.index[w.index >= start][::step_weeks]:
        if pd.isna(realised.get(d)):
            continue
        res = engine.find(ctx, d, horizon_weeks=horizon_weeks, with_paths=False, bootstrap=False, **find_kw)
        if res is None or horizon_weeks not in res.outcomes.index:
            continue
        o = res.outcomes.loc[horizon_weeks]
        rows.append({"date": d, "pred_median": o["median"], "pred_hit_rate": o["hit_rate"],
                     "base_median": o["base_median"], "base_hit_rate": o["base_hit_rate"],
                     "realised": realised[d]})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def score(bt: pd.DataFrame) -> dict:
    """Out-of-sample summary of a backtest frame."""
    if bt.empty:
        return {"n": 0}
    up = bt["realised"] > 0
    analog_call = bt["pred_median"] > 0
    base_call = bt["base_median"] > 0
    ic = bt["pred_median"].corr(bt["realised"], method="spearman")
    # Calibration: realised up-frequency within buckets of predicted hit rate
    buckets = pd.cut(bt["pred_hit_rate"], [0, 0.35, 0.5, 0.65, 1.0], include_lowest=True)
    calib = bt.groupby(buckets, observed=True).agg(predicted=("pred_hit_rate", "mean"),
                                                  realised=("realised", lambda r: (r > 0).mean()),
                                                  weeks=("realised", "size"))
    # Strategy view: long when analogs say up, flat otherwise, vs. always long
    strat = np.where(analog_call, bt["realised"], 0.0)
    return {
        "n": len(bt),
        "direction_accuracy": float((analog_call == up).mean()),
        "base_direction_accuracy": float((base_call == up).mean()),
        "always_up_accuracy": float(up.mean()),
        "ic_spearman": float(ic),
        "mean_when_analogs_up": float(bt.loc[analog_call, "realised"].mean()) if analog_call.any() else np.nan,
        "mean_when_analogs_down": float(bt.loc[~analog_call, "realised"].mean()) if (~analog_call).any() else np.nan,
        "long_flat_mean": float(np.mean(strat)),
        "always_long_mean": float(bt["realised"].mean()),
        "calibration": calib,
    }


def verdict(sc: dict) -> str:
    """Plain-English read of a score dict for the dashboard and the brief."""
    if sc.get("n", 0) == 0:
        return "Not enough history to backtest."
    lift = sc["direction_accuracy"] - max(sc["base_direction_accuracy"], sc["always_up_accuracy"])
    ic = sc["ic_spearman"]
    if lift > 0.03 and ic > 0.05:
        return (f"Useful: analog direction calls beat the base rate by {lift:+.0%} out of sample "
                f"(IC {ic:.2f}). Weight the analog read, but size for being wrong.")
    if lift > 0.015 or ic > 0.03:
        return (f"Weak: a small out-of-sample edge (accuracy {lift:+.0%} vs. base, IC {ic:.2f}). "
                "Use the analogs for context and risk ranges, not as a signal on their own.")
    return (f"No edge: analog direction calls did not beat the base rate out of sample "
            f"(accuracy {lift:+.0%}, IC {ic:.2f}). Use them only for ranges (MAE/MFE, vol), not direction.")
