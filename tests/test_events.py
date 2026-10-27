"""Shock channels, the event catalogue and event studies (offline, synthetic data)."""

import numpy as np
import pandas as pd
import pytest

from slv_dashboard import events
from slv_dashboard.analogs import engine, setups
from slv_dashboard.analogs import features as feat
from slv_dashboard.data import gpr
from slv_dashboard.models import alerts, channels


def _daily(n=900, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    walk = lambda s0, vol: s0 * np.exp(np.cumsum(rng.normal(0, vol, n)))  # noqa: E731
    return pd.DataFrame({
        "gold": walk(1200, 0.01), "silver": walk(16, 0.015), "oil": walk(60, 0.02), "copper": walk(3, 0.012),
        "spx": walk(2000, 0.01), "dollar_broad": walk(100, 0.003), "vix": 15 * np.exp(rng.normal(0, 0.1, n)),
        "real_yield_10y": 0.5 + np.cumsum(rng.normal(0, 0.02, n)),
        "nominal_2y": 1.0 + np.cumsum(rng.normal(0, 0.02, n)),
        "breakeven_10y": 2.0 + np.cumsum(rng.normal(0, 0.01, n)),
        "mm_net_pct_oi": rng.normal(10, 5, n),
    }, index=idx)


def _shock(d, cols_moves: dict, days=20):
    """Apply a ramp over the last ``days`` rows: log moves for prices, level moves for rates."""
    d = d.copy()
    ramp = np.linspace(0, 1, days)
    for col, mv in cols_moves.items():
        if col in ("real_yield_10y", "nominal_2y", "breakeven_10y"):
            d.iloc[-days:, d.columns.get_loc(col)] += mv * ramp
        else:
            d.iloc[-days:, d.columns.get_loc(col)] *= np.exp(mv * ramp)
    return d


@pytest.mark.parametrize("moves,expected", [
    ({"oil": 0.35, "breakeven_10y": 0.4, "nominal_2y": 0.5, "dollar_broad": 0.03}, "inflation"),
    ({"gold": 0.12, "real_yield_10y": -0.5, "spx": -0.08, "vix": 0.6}, "haven"),
    ({"nominal_2y": -0.7, "real_yield_10y": -0.5, "dollar_broad": -0.04, "gold": 0.05}, "dovish"),
    ({"vix": 1.0, "spx": -0.2, "copper": -0.15, "oil": -0.2}, "risk_off"),
])
def test_classifier_names_planted_shock(moves, expected):
    ch = channels.classify(_shock(_daily(), moves))
    assert ch["channel"].iloc[-1] == expected


def test_classifier_has_no_lookahead_and_is_quiet_on_noise():
    d = _daily()
    full = channels.classify(d)
    cut = channels.classify(d.iloc[:600])
    pd.testing.assert_frame_equal(full.iloc[:600], cut)
    assert (full["channel"].dropna() == "quiet").mean() > 0.5


def test_fed_moves_from_target_series():
    idx = pd.to_datetime(["2008-12-10", "2008-12-15", "2008-12-16", "2015-12-16", "2015-12-17", "2016-12-15"])
    macro = pd.DataFrame({"fed_target_old": [1.0, 1.0, np.nan, np.nan, np.nan, np.nan],
                          "fed_target_upper": [np.nan, np.nan, 0.25, 0.25, 0.50, 0.75]}, index=idx)
    fm = events.fed_moves(macro)
    assert list(fm["type"]) == ["fed_cut", "fed_hike", "fed_hike"]
    assert fm.iloc[0]["title"].startswith("Fed cuts 75bp")
    assert list(fm["date"]) == [pd.Timestamp("2008-12-16"), pd.Timestamp("2015-12-17"), pd.Timestamp("2016-12-15")]


def test_detected_shocks_use_episodes_and_thresholds():
    d = _daily(1500)
    calm = 60 * np.exp(np.cumsum(np.random.default_rng(9).normal(0, 0.005, len(d))))
    calm[1000:1020] *= np.exp(np.linspace(0, 0.4, 20))   # +49% in 4 weeks
    calm[1020:] *= np.exp(0.4)
    d["oil"] = calm
    d.iloc[1200, d.columns.get_loc("vix")] = 40.0
    days = pd.date_range("2005-01-01", d.index[-1])
    g = pd.DataFrame({"gpr": 100.0}, index=days)
    g.loc["2019-06-01":"2019-06-10", "gpr"] = 600.0
    det = events.detected(d, g)
    oil = det[det["type"] == "oil_spike"]
    assert len(oil) == 1 and d.index[1000] < oil["date"].iloc[0] <= d.index[1019]
    assert (det["type"] == "vol_spike").sum() == 1
    spikes = det[det["type"] == "gpr_spike"]
    assert len(spikes) == 1 and spikes["date"].iloc[0].year == 2019


def test_seed_catalogue_is_valid():
    s = events.seed()
    assert list(s.columns) == events.COLUMNS
    assert s["date"].notna().all() and s["title"].notna().all()
    assert set(s["category"]) <= set(events.CATEGORY_LABELS)
    assert {"war_onset", "tariff", "qe"} <= set(s["type"])
    assert not s.duplicated(["date", "title"]).any()


def test_event_paths_are_relative_to_prior_close():
    idx = pd.bdate_range("2020-01-01", periods=200)
    price = pd.Series(np.linspace(100, 199, 200), index=idx)
    p = events.paths(price, [idx[100]], before=5, after=10)
    assert p.index[0] == -5 and p.index[-1] == 10
    assert p.loc[-1].iloc[0] == pytest.approx(0.0)
    assert p.loc[0].iloc[0] == pytest.approx(price.iloc[100] / price.iloc[99] - 1)


def test_event_setups_fire_in_event_weeks_and_scan_includes_them():
    d = _daily(1500)
    ctx = engine.AnalogContext.from_daily(d, "silver")
    wk = ctx.weekly.index
    dates = [wk[i] - pd.Timedelta(days=1) for i in (100, 140, 180, 220, len(wk) - 1)]
    cat = pd.DataFrame({"date": dates, "category": "geopolitics", "type": "war_onset", "title": "x",
                        "region": "", "source": "test"})
    ev = events.event_setups(cat)
    assert [s.key for s in ev] == ["event_war_onset"]
    scan = setups.scan(ctx, setups.SETUPS + ev)
    row = scan[(scan["key"] == "event_war_onset") & (scan["horizon_weeks"] == 4)].iloc[0]
    assert row["live"] and row["n"] == 4      # the live (latest) event has no 4-week outcome yet
    assert scan["key"].str.startswith("channel_").any()


def test_features_include_events_group_and_channel():
    d = _daily(1500)
    days = pd.date_range(d.index[0], d.index[-1])
    d["gpr"] = pd.Series(100.0, index=days).reindex(d.index)
    w = feat.build(d, "silver")
    assert {"gpr_pctile", "gpr_chg_4w", "oil_ret_4w", "vix_pctile", "channel"} <= set(w.columns)
    res = engine.find(engine.AnalogContext.from_daily(d, "silver"), horizon_weeks=13)
    assert "channel" in res.matches.columns
    assert set(feat.GROUPS["events"]) <= set(res.features_used)


def test_gpr_parse_and_alerts():
    raw = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=3), "GPRD": [100, 200, 300],
                        "GPRD_ACT": [1, 2, 3], "GPRD_THREAT": [4, 5, 6], "event": [None, "Something", None]})
    df, ev = gpr.parse(raw)
    assert list(df.columns) == ["gpr", "gpr_act", "gpr_threat"] and ev["title"].tolist() == ["Something"]

    idx = pd.bdate_range("2020-01-01", periods=300)
    daily = pd.DataFrame({"gpr": np.r_[np.full(280, 100.0), np.full(20, 400.0)]}, index=idx)
    assert alerts.geopolitical_risk(daily).title == "Geopolitical risk elevated"
    assert alerts.geopolitical_risk(daily.assign(gpr=100.0)) is None
    row = pd.Series({"channel": "inflation", "channel_score": 1.4})
    assert "inflation shock" in alerts.shock_channel(row).title
    assert alerts.shock_channel(pd.Series({"channel": "quiet", "channel_score": 0.3})) is None
