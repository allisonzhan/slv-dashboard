"""Analog engine, setups and backtest on synthetic data with known structure."""

import numpy as np
import pandas as pd
import pytest

from slv_dashboard.analogs import backtest, engine, setups
from slv_dashboard.analogs import features as feat


def _daily(n=3000, seed=0, planted=0.0):
    """Synthetic aligned daily frame.

    Positioning is a mean-reverting AR(1) process. With ``planted`` > 0, silver drifts
    up while managed money is short and down while it's long, so positioning
    analogs should find a real edge; with planted=0 silver is a random walk.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2005-01-03", periods=n)
    mm = np.zeros(n)
    for i in range(1, n):
        mm[i] = 0.98 * mm[i - 1] + rng.normal(0, 3)
    drift = -planted * np.sign(mm)
    silver = 20 * np.exp(np.cumsum(drift + rng.normal(0, 0.015, n)))
    gold = 1000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return pd.DataFrame({
        "silver": silver, "gold": gold,
        "copper": 3 * np.exp(np.cumsum(rng.normal(0, 0.012, n))),
        "real_yield_10y": 1 + np.cumsum(rng.normal(0, 0.03, n)),
        "dollar_broad": 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n))),
        "mm_net_pct_oi": mm,
    }, index=idx)


def test_features_have_no_lookahead():
    daily = _daily(1500)
    full = feat.build(daily)
    cut = full.index[200]
    truncated = feat.build(daily[daily.index <= cut])
    cols = feat.all_features()
    pd.testing.assert_series_equal(full.loc[cut, cols], truncated.loc[cut, cols], check_names=False)


def test_weekly_rows_are_last_trading_day():
    daily = _daily(400).iloc[:-2]  # end mid-week
    w = feat.build(daily)
    assert w.index[-1] == daily.index[-1]
    assert (w.index[:-1].dayofweek == 4).all()


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.linspace(10, 20, 100))
    assert feat.rsi(up).iloc[-1] == pytest.approx(100)
    r = feat.rsi(pd.Series(np.random.default_rng(1).normal(0, 1, 500)).cumsum() + 100)
    assert r.dropna().between(0, 100).all()


def test_horizon_exclusion_and_declustering():
    ctx = engine.AnalogContext.from_daily(_daily(), "silver")
    res = engine.find(ctx, horizon_weeks=13, k=15, min_gap_weeks=8)
    rows = ctx.weekly.index.get_indexer(res.matches.index)
    qi = ctx.weekly.index.get_loc(res.query_date)
    assert (rows <= qi - 13).all()
    gaps = np.diff(np.sort(res.matches.index.values)).astype("timedelta64[D]").astype(int)
    assert (gaps >= 56).all()
    assert len(res.matches) == 15
    assert set(res.outcomes.index) == {1, 4, 13}


def test_engine_finds_planted_edge():
    ctx = engine.AnalogContext.from_daily(_daily(planted=0.003, seed=2), "silver")
    mm = ctx.weekly["mm_net_pct_oi"].iloc[300:]
    kw = dict(groups=("positioning",), shape_weight=0.0, horizon_weeks=4)
    # Planted drift: silver rises while specs are short and falls while they're long
    short = engine.find(ctx, mm.idxmin(), **kw).outcomes.loc[4]
    long = engine.find(ctx, mm.idxmax(), **kw).outcomes.loc[4]
    assert short["median"] - long["median"] > 0.05
    assert short["hit_rate"] > long["hit_rate"] + 0.3
    assert long["edge_median"] < 0 < short["edge_median"]


def test_backtest_finds_planted_edge_and_not_noise():
    kw = dict(groups=("positioning",), shape_weight=0.0, k=15)
    planted = engine.AnalogContext.from_daily(_daily(planted=0.004, seed=3), "silver")
    sc = backtest.score(backtest.run(planted, 4, start="2009-01-01", step_weeks=2, **kw))
    assert sc["ic_spearman"] > 0.3
    assert sc["direction_accuracy"] > sc["always_up_accuracy"]

    noise = engine.AnalogContext.from_daily(_daily(planted=0.0, seed=4), "silver")
    sc0 = backtest.score(backtest.run(noise, 4, start="2009-01-01", step_weeks=2, **kw))
    assert abs(sc0["ic_spearman"]) < 0.15
    assert "No edge" in backtest.verdict(sc0) or "Weak" in backtest.verdict(sc0)


def test_triggers_take_first_week_of_each_episode():
    idx = pd.date_range("2020-01-03", periods=40, freq="W-FRI")
    mask = pd.Series(False, index=idx)
    mask.iloc[[2, 3, 4, 8, 20, 21]] = True   # 8 is within 8 weeks of the 2-4 run
    got = setups.triggers(mask, min_gap_weeks=8)
    assert list(got) == [idx[2], idx[20]]


def test_scan_reports_live_setup():
    daily = _daily(2000, seed=5)
    daily.iloc[-130:, daily.columns.get_loc("silver")] *= np.linspace(1, 0.6, 130)  # slide into a drawdown
    ctx = engine.AnalogContext.from_daily(daily, "silver")
    scan = setups.scan(ctx)
    live = scan[scan["live"]]
    assert "deep_drawdown" in set(live["key"])
    assert {"hit_rate", "edge_median", "p_value"} <= set(scan.columns)


def test_target_series_ratio():
    daily = _daily(300)
    gsr = feat.target_series(daily, "gsr")
    assert gsr.iloc[-1] == pytest.approx(daily["gold"].iloc[-1] / daily["silver"].iloc[-1])
    with pytest.raises(KeyError):
        feat.target_series(daily, "platinum")
