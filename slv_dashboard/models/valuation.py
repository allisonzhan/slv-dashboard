"""Is silver rich or cheap against what its drivers say it should be?

Fair value: a rolling regression of log silver on log gold, the 10Y real
yield, log broad dollar and log copper, in levels, over a 3-year window of
weekly data. The residual is how far price sits from that fit, and its
z-score (vs. the window's residual spread) is the rich/cheap read. Levels
regressions drift, so read it as "stretched vs. recent relationships", not
an absolute anchor; large z-scores have tended to mean-revert, small ones
mean little.

Gold/silver ratio: today's ratio against its own rolling 3-year
distribution (10th/50th/90th percentile bands).
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.rolling import RollingOLS

WINDOW_WEEKS = 156
DRIVERS = ["log_gold", "real_yield_10y", "log_dollar", "log_copper"]


def weekly_levels(daily: pd.DataFrame) -> pd.DataFrame:
    cols = ["silver", "gold", "copper", "dollar_broad", "real_yield_10y"]
    w = daily[cols].resample("W-FRI").last().dropna()
    if len(w) and w.index[-1] > daily.index.max():   # week in progress: label it with today, not Friday
        w = w.rename(index={w.index[-1]: daily.index.max()})
    return pd.DataFrame({
        "log_silver": np.log(w["silver"]),
        "log_gold": np.log(w["gold"]),
        "real_yield_10y": w["real_yield_10y"],
        "log_dollar": np.log(w["dollar_broad"]),
        "log_copper": np.log(w["copper"]),
        "silver": w["silver"],
    })


def fair_value(daily: pd.DataFrame, window: int = WINDOW_WEEKS) -> pd.DataFrame:
    """Weekly fair value, residual (%) and residual z-score, each from the window ending that week."""
    lv = weekly_levels(daily)
    X = sm.add_constant(lv[DRIVERS])
    res = RollingOLS(lv["log_silver"], X, window=window).fit()
    params = res.params
    fitted = (X * params).sum(axis=1, min_count=1)
    resid = lv["log_silver"] - fitted
    # Residual spread inside each window: sqrt(SSR / dof) from the rolling fit
    sigma = np.sqrt(res.ssr / (window - len(DRIVERS) - 1))
    out = pd.DataFrame({
        "silver": lv["silver"],
        "fair_value": np.exp(fitted),
        "residual_pct": np.exp(resid) - 1,
        "z": resid / sigma,
        "r2": res.rsquared,
    }).dropna()
    for d in DRIVERS:
        out[f"beta_{d}"] = params[d]
    out["band_lo"] = out["fair_value"] * np.exp(-sigma.reindex(out.index))
    out["band_hi"] = out["fair_value"] * np.exp(sigma.reindex(out.index))
    return out


def gsr_bands(daily: pd.DataFrame, window: int = WINDOW_WEEKS) -> pd.DataFrame:
    gsr = (daily["gold"] / daily["silver"]).resample("W-FRI").last().dropna()
    if len(gsr) and gsr.index[-1] > daily.index.max():
        gsr = gsr.rename(index={gsr.index[-1]: daily.index.max()})
    roll = gsr.rolling(window, min_periods=104)
    return pd.DataFrame({
        "gsr": gsr,
        "p10": roll.quantile(0.10),
        "p50": roll.quantile(0.50),
        "p90": roll.quantile(0.90),
        "pctile": roll.rank(pct=True),
    }).dropna()


def read(fv: pd.DataFrame) -> str:
    """Plain-English verdict on the latest fair-value z-score."""
    z = fv["z"].iloc[-1]
    gap = fv["residual_pct"].iloc[-1]
    if z >= 2:
        return f"Rich: {gap:+.0%} above driver fair value (z {z:+.1f}). Stretched; mean reversion risk."
    if z >= 1:
        return f"Somewhat rich: {gap:+.0%} vs. fair value (z {z:+.1f})."
    if z <= -2:
        return f"Cheap: {gap:+.0%} below driver fair value (z {z:+.1f}). Stretched; catch-up potential."
    if z <= -1:
        return f"Somewhat cheap: {gap:+.0%} vs. fair value (z {z:+.1f})."
    return f"Near fair value ({gap:+.0%}, z {z:+.1f})."
