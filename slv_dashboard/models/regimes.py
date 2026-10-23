"""Regime views on silver, meant to be read together.

- rule_based(): monetary vs. industrial. How much of silver copper explains
  relative to gold, ranked against history. Transparent and easy to explain
  in a pitch.
- markov(): calm vs. stressed. Two-regime Markov-switching regression of
  silver on gold and copper with regime-specific betas and volatility.
  On 2010-2026 weekly data the regimes separate by volatility, with silver
  more sensitive to both gold and copper in the stressed regime, so they
  are labelled by volatility rather than as monetary/industrial.
"""

import numpy as np
import pandas as pd
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

from slv_dashboard.config import REGIME_MIN_HISTORY_WEEKS

MONETARY, INDUSTRIAL, MIXED = "monetary", "industrial", "mixed"
CALM, STRESSED = "calm", "stressed"

# Clip the most extreme 0.5% of weeks on each tail before the Markov fit, so a
# single crash week (e.g. 2026-01-30) can't become a regime of its own
MARKOV_CLIP_Q = 0.005


def _rolling_r2(y: pd.Series, x: pd.Series, window: int) -> pd.Series:
    # Univariate OLS R^2 is the squared correlation
    return y.rolling(window).corr(x) ** 2


def rule_based(returns: pd.DataFrame, window: int, min_history: int = REGIME_MIN_HISTORY_WEEKS) -> pd.DataFrame:
    """Label each window by copper's share of explanatory power vs. its own history.

    Gold explains more of silver than copper almost always (about 90% of
    52-week windows since 2010), so comparing the two R^2s directly would say
    "monetary" nearly every week. Instead, industrial_share =
    r2_copper / (r2_gold + r2_copper) is ranked against all earlier windows
    (expanding, so no look-ahead): top third -> industrial, bottom third ->
    monetary, else mixed. Weeks before min_history windows exist are dropped.

    Because labels are relative to history, a regime that lasts for years
    becomes the norm and its labels drift toward mixed. Read the label as
    "more industrial than usual", and check industrial_share for the level.
    """
    y = returns["silver_ret"]
    out = pd.DataFrame({
        "r2_gold": _rolling_r2(y, returns["gold_ret"], window),
        "r2_copper": _rolling_r2(y, returns["copper_ret"], window),
    }).dropna()
    out["industrial_share"] = out["r2_copper"] / (out["r2_gold"] + out["r2_copper"])
    out["share_pctile"] = out["industrial_share"].expanding(min_history).rank(pct=True)
    out = out.dropna()
    out["regime"] = np.select(
        [out["share_pctile"] > 2 / 3, out["share_pctile"] < 1 / 3], [INDUSTRIAL, MONETARY], default=MIXED
    )
    return out


def markov(returns: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Smoothed probability of the stressed regime per week.

    Returns are scaled to percent first; on raw log returns the variances are
    so small that the optimizer collapses onto degenerate one-week regimes.
    The fitted betas and weekly vol per regime are in ``.attrs["regimes"]``.
    """
    cols = ["silver_ret", "gold_ret", "copper_ret"]
    pct = returns[cols] * 100
    pct = pct.clip(pct.quantile(MARKOV_CLIP_Q), pct.quantile(1 - MARKOV_CLIP_Q), axis=1)

    model = MarkovRegression(pct["silver_ret"], k_regimes=2, exog=pct[["gold_ret", "copper_ret"]],
                             switching_variance=True)
    np.random.seed(seed)
    res = model.fit(search_reps=20, disp=False)

    p = res.params
    sigma = [float(np.sqrt(p[f"sigma2[{k}]"])) for k in range(2)]
    stressed_k = int(np.argmax(sigma))
    probs = res.smoothed_marginal_probabilities

    out = pd.DataFrame({"p_stressed": probs[stressed_k]}, index=returns.index)
    out["regime"] = np.where(out["p_stressed"] > 0.5, STRESSED, CALM)

    def describe(k: int) -> dict:
        return {
            "gold_beta": float(p[f"x1[{k}]"]),
            "copper_beta": float(p[f"x2[{k}]"]),
            "weekly_vol_pct": sigma[k],
            "expected_weeks": float(res.expected_durations[k]),
        }

    out.attrs["regimes"] = {STRESSED: describe(stressed_k), CALM: describe(1 - stressed_k)}
    return out
