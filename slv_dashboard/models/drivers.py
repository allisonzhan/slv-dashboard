"""Silver driver regressions on weekly returns.

Two specifications:
- MACRO: real-yield change, dollar return, copper return. Asks what moves
  silver once gold is left out, so the monetary channel shows up in the
  real-yield and dollar betas.
- WITH_GOLD: adds gold return. Gold soaks up most of the monetary channel,
  so copper's beta here is silver's industrial sensitivity beyond gold.
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.rolling import RollingOLS
from statsmodels.stats.diagnostic import breaks_cusumolsresid

MACRO = ["real_yield_chg", "dollar_ret", "copper_ret"]
WITH_GOLD = MACRO + ["gold_ret"]
TARGET = "silver_ret"


def weekly_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Friday-to-Friday log returns (and real-yield change in percentage points).

    A week still in progress is dropped, so mid-week runs don't treat a
    partial week as complete.
    """
    cols = ["silver", "gold", "copper", "dollar_broad", "real_yield_10y"]
    last_day = df.index.max()
    if last_day.dayofweek != 4:  # not a Friday: the final bucket is incomplete
        df = df[df.index <= last_day - pd.offsets.Week(weekday=4)]
    w = df[cols].resample("W-FRI").last()
    out = pd.DataFrame(index=w.index)
    for col, name in (("silver", "silver_ret"), ("gold", "gold_ret"), ("copper", "copper_ret"), ("dollar_broad", "dollar_ret")):
        out[name] = np.log(w[col]).diff()
    out["real_yield_chg"] = w["real_yield_10y"].diff()
    return out.dropna()


def full_sample(returns: pd.DataFrame, drivers: list[str] = MACRO, hac_lags: int = 4):
    """OLS with Newey-West (HAC) standard errors."""
    X = sm.add_constant(returns[drivers])
    return sm.OLS(returns[TARGET], X).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})


def rolling_betas(returns: pd.DataFrame, window: int, drivers: list[str] = MACRO) -> pd.DataFrame:
    """Rolling OLS betas plus R^2, indexed by the window's last week."""
    X = sm.add_constant(returns[drivers])
    res = RollingOLS(returns[TARGET], X, window=window).fit()
    out = res.params.drop(columns="const")
    out["r2"] = res.rsquared
    return out.dropna()


def stability_test(returns: pd.DataFrame, drivers: list[str] = MACRO) -> dict:
    """CUSUM test on OLS residuals: a small p-value means the relationship drifted."""
    res = sm.OLS(returns[TARGET], sm.add_constant(returns[drivers])).fit()
    stat, pvalue, _ = breaks_cusumolsresid(res.resid, ddof=len(drivers) + 1)
    return {"cusum_stat": float(stat), "p_value": float(pvalue)}
