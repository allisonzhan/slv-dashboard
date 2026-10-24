"""Model tests on synthetic data with known structure."""

import warnings

import numpy as np
import pandas as pd
import pytest

from slv_dashboard.models import drivers, regimes


def _synthetic_returns(n=600, seed=0, copper_beta=0.3, gold_beta=1.3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2012-01-06", periods=n, freq="W-FRI")
    r = pd.DataFrame({
        "gold_ret": rng.normal(0, 0.02, n),
        "copper_ret": rng.normal(0, 0.025, n),
        "dollar_ret": rng.normal(0, 0.008, n),
        "real_yield_chg": rng.normal(0, 0.08, n),
    }, index=idx)
    r["silver_ret"] = gold_beta * r["gold_ret"] + copper_beta * r["copper_ret"] + rng.normal(0, 0.01, n)
    return r


def test_weekly_returns_drops_incomplete_week():
    days = pd.bdate_range("2026-09-28", "2026-10-22")  # ends on a Thursday
    df = pd.DataFrame({c: np.linspace(1, 2, len(days)) for c in
                       ("silver", "gold", "copper", "dollar_broad", "real_yield_10y")}, index=days)
    w = drivers.weekly_returns(df)
    assert w.index.max() == pd.Timestamp("2026-10-16")


def test_full_sample_recovers_betas():
    res = drivers.full_sample(_synthetic_returns(), drivers.WITH_GOLD)
    assert res.params["gold_ret"] == pytest.approx(1.3, abs=0.05)
    assert res.params["copper_ret"] == pytest.approx(0.3, abs=0.05)
    assert abs(res.params["dollar_ret"]) < 0.2


def test_rolling_betas_track_a_structural_change():
    first = _synthetic_returns(300, seed=1, copper_beta=0.1)
    second = _synthetic_returns(300, seed=2, copper_beta=1.0)
    second.index = pd.date_range(first.index[-1] + pd.Timedelta(weeks=1), periods=300, freq="W-FRI")
    betas = drivers.rolling_betas(pd.concat([first, second]), 52, drivers.WITH_GOLD)
    assert betas["copper_ret"].iloc[0] == pytest.approx(0.1, abs=0.1)
    assert betas["copper_ret"].iloc[-1] == pytest.approx(1.0, abs=0.1)


def _gold_then_copper_led():
    gold_led = _synthetic_returns(300, seed=6, copper_beta=0.1, gold_beta=1.5)
    copper_led = _synthetic_returns(300, seed=7, copper_beta=1.5, gold_beta=0.3)
    copper_led.index = pd.date_range(gold_led.index[-1] + pd.Timedelta(weeks=1), periods=300, freq="W-FRI")
    return pd.concat([gold_led, copper_led])


def test_rule_based_flags_shift_to_industrial():
    r = _gold_then_copper_led()
    rule = regimes.rule_based(r, 52)
    # Once the 52-week window sits fully in the copper-led half, the next ~100
    # weeks should read industrial. Later on, the copper-led history itself
    # becomes "normal" and labels drift toward mixed (documented in rule_based).
    shift = rule.loc[r.index[352]:r.index[450]]
    assert (shift["regime"] == regimes.INDUSTRIAL).mean() > 0.9


def test_rule_based_has_no_lookahead():
    r = _gold_then_copper_led()
    full = regimes.rule_based(r, 52)
    truncated = regimes.rule_based(r.iloc[:400], 52)
    pd.testing.assert_series_equal(full["regime"].loc[truncated.index], truncated["regime"])


def test_markov_separates_calm_and_stressed_weeks():
    rng = np.random.default_rng(3)
    calm = _synthetic_returns(400, seed=4)
    stressed = _synthetic_returns(150, seed=5, gold_beta=1.9)
    stressed["silver_ret"] += rng.normal(0, 0.04, 150)
    stressed.index = pd.date_range(calm.index[-1] + pd.Timedelta(weeks=1), periods=150, freq="W-FRI")
    r = pd.concat([calm, stressed])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mk = regimes.markov(r)
    assert (mk.loc[stressed.index, "regime"] == regimes.STRESSED).mean() > 0.8
    assert (mk.loc[calm.index, "regime"] == regimes.CALM).mean() > 0.8
    info = mk.attrs["regimes"]
    assert info[regimes.STRESSED]["weekly_vol_pct"] > info[regimes.CALM]["weekly_vol_pct"]
