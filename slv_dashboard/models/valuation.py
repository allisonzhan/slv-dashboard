"""Is the metal rich or cheap against what its drivers say it should be?

Fair value: a rolling regression of the log metal price on its drivers, in
levels, over a 3-year window of weekly data:
  silver  log gold, 10Y real yield, log broad dollar, log copper
  gold    10Y real yield, log broad dollar, 10Y breakeven inflation
The residual is how far price sits from that fit, and its z-score (vs. the
window's residual spread) is the rich/cheap read. Levels regressions drift,
so read it as "stretched vs. recent relationships", not an absolute anchor;
large z-scores have tended to mean-revert, small ones mean little. Gold's
link to real yields loosened after 2022 (central-bank buying), so its R²
deserves a look before leaning on the z-score.

The fit runs on the metal's futures price. For an ETF the fair value and
band are rescaled to the ETF's own price (same residual in percent).

Gold/silver ratio: today's ratio against its own rolling 3-year
distribution (10th/50th/90th percentile bands).
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.rolling import RollingOLS

from slv_dashboard import instruments

WINDOW_WEEKS = 156
DRIVERS = {
    "silver": ["log_gold", "real_yield_10y", "log_dollar", "log_copper"],
    "gold": ["real_yield_10y", "log_dollar", "breakeven_10y"],
}


def _weekly(s: pd.DataFrame | pd.Series, daily: pd.DataFrame):
    w = s.resample("W-FRI").last()
    if len(w) and w.index[-1] > daily.index.max():   # week in progress: label it with today, not Friday
        w = w.rename(index={w.index[-1]: daily.index.max()})
    return w


def weekly_levels(daily: pd.DataFrame, metal: str = "silver") -> pd.DataFrame:
    w = _weekly(daily, daily)
    out = pd.DataFrame({
        "price": w[metal],
        "log_price": np.log(w[metal]),
        "log_gold": np.log(w["gold"]),
        "real_yield_10y": w["real_yield_10y"],
        "log_dollar": np.log(w["dollar_broad"]),
        "log_copper": np.log(w["copper"]) if "copper" in w else np.nan,
        "breakeven_10y": w["breakeven_10y"] if "breakeven_10y" in w else np.nan,
    })
    return out.dropna(subset=["log_price"] + DRIVERS[metal])


def fair_value(daily: pd.DataFrame, instrument: str = "silver", window: int = WINDOW_WEEKS) -> pd.DataFrame:
    """Weekly fair value, residual (%) and residual z-score, each from the window ending that week.

    ``price``, ``fair_value`` and the band are in the instrument's own units.
    """
    inst = instruments.get(instrument)
    drivers = DRIVERS[inst.metal]
    lv = weekly_levels(daily, inst.metal)
    X = sm.add_constant(lv[drivers])
    res = RollingOLS(lv["log_price"], X, window=window).fit()
    params = res.params
    fitted = (X * params).sum(axis=1, min_count=1)
    resid = lv["log_price"] - fitted
    # Residual spread inside each window: sqrt(SSR / dof) from the rolling fit
    sigma = np.sqrt(res.ssr / (window - len(drivers) - 1))
    out = pd.DataFrame({
        "price": lv["price"],
        "fair_value": np.exp(fitted),
        "residual_pct": np.exp(resid) - 1,
        "z": resid / sigma,
        "r2": res.rsquared,
    }).dropna()
    for d in drivers:
        out[f"beta_{d}"] = params[d]
    out["band_lo"] = out["fair_value"] * np.exp(-sigma.reindex(out.index))
    out["band_hi"] = out["fair_value"] * np.exp(sigma.reindex(out.index))

    if inst.kind == "etf":
        # Same residual, expressed in the ETF's price: scale by ETF/futures on each week
        etf = _weekly(instruments.price(daily, instrument), daily).reindex(out.index)
        scale = etf / out["price"]
        for col in ("price", "fair_value", "band_lo", "band_hi"):
            out[col] = out[col] * scale
        out = out.dropna(subset=["price"])
    out.attrs["drivers"] = drivers
    return out


def gsr_bands(daily: pd.DataFrame, window: int = WINDOW_WEEKS) -> pd.DataFrame:
    gsr = _weekly(daily["gold"] / daily["silver"], daily).dropna()
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
