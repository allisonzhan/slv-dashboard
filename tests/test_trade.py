"""Fair-value model, scorecard and trade plan on synthetic inputs."""

import numpy as np
import pandas as pd
import pytest

from slv_dashboard.models import trade, valuation


def _cointegrated(n_days=2500, seed=0, shock=0.0):
    """Silver tied to gold and copper in levels, plus small noise; ``shock`` bumps the final week."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2014-01-01", periods=n_days)
    lg = np.log(1200) + np.cumsum(rng.normal(0, 0.01, n_days))
    lc = np.log(3) + np.cumsum(rng.normal(0, 0.012, n_days))
    ry = 1 + np.cumsum(rng.normal(0, 0.02, n_days))
    ld = np.log(100) + np.cumsum(rng.normal(0, 0.003, n_days))
    ls = -4.0 + 1.0 * lg + 0.3 * lc - 0.1 * ry + rng.normal(0, 0.01, n_days)
    ls[-5:] += shock
    return pd.DataFrame({"silver": np.exp(ls), "gold": np.exp(lg), "copper": np.exp(lc),
                         "real_yield_10y": ry, "dollar_broad": np.exp(ld)}, index=idx)


def test_fair_value_recovers_relationship_and_flags_dislocation():
    fv = valuation.fair_value(_cointegrated())
    assert fv["beta_log_gold"].iloc[-1] == pytest.approx(1.0, abs=0.05)
    assert fv["beta_log_copper"].iloc[-1] == pytest.approx(0.3, abs=0.05)
    assert abs(fv["z"].iloc[-1]) < 3
    rich = valuation.fair_value(_cointegrated(shock=0.10))
    assert rich["z"].iloc[-1] > 3
    assert valuation.read(rich).startswith("Rich")


def test_week_in_progress_is_labelled_with_last_date():
    d = _cointegrated().iloc[:-2]   # end mid-week
    assert valuation.gsr_bands(d).index[-1] == d.index[-1]
    assert valuation.fair_value(d).index[-1] == d.index[-1]


def _outcomes(edge=0.08, p=0.05):
    return pd.DataFrame({
        "median": [0.02 + edge], "base_median": [0.02], "edge_median": [edge], "hit_rate": [0.7], "p_value": [p],
        "mae_median": [-0.04], "mae_q25": [-0.09], "mfe_median": [0.10], "mfe_q75": [0.16], "fwd_vol_median": [0.30],
    }, index=[13])


def _scan(views):
    return pd.DataFrame({"setup": [f"s{i}" for i in range(len(views))], "view": views, "live": True,
                         "horizon_weeks": 13, "key": [f"k{i}" for i in range(len(views))]})


def test_scorecard_scores_each_lens():
    fv = pd.DataFrame({"z": [-2.1], "residual_pct": [-0.12]})
    feats = pd.Series({"mm_pctile": 0.05, "ry_chg_13w": -0.30, "usd_ret_13w": -0.04})
    curve = pd.DataFrame({"front": [50.0], "next": [49.8], "backwardation": [True], "implied_lease_pct": [6.0]})
    card = trade.build_scorecard(outcomes=_outcomes(), backtest_has_edge=True, scan=_scan(["bullish", "bullish"]),
                                 fv=fv, features=feats, curve=curve)
    scores = {s.lens: s.score for s in card.scores}
    assert scores == {"analogs": 2, "setups": 2, "valuation": 2, "positioning": 2, "macro": 2, "curve": 2}
    assert card.stance == "bullish" and card.total == 12


def test_analog_score_capped_without_backtest_edge():
    s = trade.score_analogs(_outcomes(), backtest_has_edge=False)
    assert s.score == 1 and "capped" in s.reason


def test_long_plan_uses_analog_excursions():
    card = trade.Scorecard([trade.Score("analogs", 2, ""), trade.Score("macro", 2, "")])
    tp = trade.plan(card, _outcomes(), 50.0, risk_pct=1.0)
    assert tp.stop == pytest.approx(50 * (1 - 0.09))
    assert tp.targets == pytest.approx([55.0, 58.0])
    assert tp.position_pct_of_book == pytest.approx(0.01 / 0.09)
    assert tp.reward_risk == pytest.approx(0.10 / 0.09)


def test_short_plan_mirrors_excursions():
    card = trade.Scorecard([trade.Score("analogs", -2, ""), trade.Score("macro", -2, "")])
    tp = trade.plan(card, _outcomes(), 50.0)
    assert tp.stance == "bearish"
    assert tp.stop == pytest.approx(50 * 1.16)
    assert tp.targets[0] == pytest.approx(50 * 0.96)


@pytest.mark.parametrize("iv,expected", [(0.20, "call spread"), (0.45, "Long SLV")])
def test_instrument_depends_on_iv_vs_realised(iv, expected):
    inst, _ = trade.suggest_instrument("bullish", iv, 0.30, None)
    assert expected in inst


def test_neutral_with_extreme_ratio_suggests_pair():
    inst, _ = trade.suggest_instrument("neutral", None, None, 0.95)
    assert "ratio" in inst and "long silver" in inst


def test_pitch_markdown_has_sections():
    card = trade.Scorecard([trade.Score("analogs", 2, "x"), trade.Score("macro", 2, "y")])
    tp = trade.plan(card, _outcomes(), 50.0)
    md = trade.pitch_markdown(card, tp, as_of=pd.Timestamp("2026-10-26"), analog_lines=["a"])
    for heading in ("## Thesis", "## Scorecard", "## Trade plan", "## Catalysts", "## What would make us wrong"):
        assert heading in md
