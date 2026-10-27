"""Instrument picker: ETF history splicing, per-metal features, setups, valuation and vehicles."""

import numpy as np
import pandas as pd
import pytest

from slv_dashboard import instruments
from slv_dashboard.analogs import engine, setups
from slv_dashboard.analogs import features as feat
from slv_dashboard.dashboard import data as dd
from slv_dashboard.models import trade, valuation


def _daily(n=2500, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2003-01-01", periods=n)
    gold = 400 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    silver = 5 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    df = pd.DataFrame({
        "silver": silver, "gold": gold,
        "copper": 1.5 * np.exp(np.cumsum(rng.normal(0, 0.012, n))),
        "real_yield_10y": 1 + np.cumsum(rng.normal(0, 0.02, n)),
        "dollar_broad": 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n))),
        "breakeven_10y": 2 + np.cumsum(rng.normal(0, 0.01, n)),
        "mm_net_pct_oi": rng.normal(10, 5, n),
        "mm_net_pct_oi_gold": rng.normal(-20, 5, n),
    }, index=idx)
    # ETFs launch partway through, tracking their metal at a fraction of an ounce
    launch = idx[800]
    df["slv"] = (df["silver"] * 0.9).where(idx >= launch)
    df["gld"] = (df["gold"] * 0.1).where(idx >= launch)
    df["iau"] = (df["gold"] * 0.02).where(idx >= launch)
    return df


def test_etf_history_is_back_extended_with_futures_returns():
    d = _daily()
    px = instruments.price(d, "gld")
    assert px.index[0] == d.index[0]                        # full history, not just since launch
    launch = instruments.launch(d, "gld")
    assert launch == d.index[800]
    pd.testing.assert_series_equal(px[px.index >= launch], d["gld"].dropna(), check_names=False)
    # Before launch the returns are the futures' returns
    before = px[px.index < launch]
    np.testing.assert_allclose(before.pct_change().dropna(), d["gold"][d.index < launch].pct_change().dropna())
    assert instruments.launch(d, "silver") is None           # futures need no splice


def test_default_instrument_is_slv():
    assert instruments.get().key == "slv"
    assert feat.TARGETS and list(feat.TARGETS)[0] == "slv"


def test_gold_targets_use_gold_positioning_and_drop_gold_return_feature():
    d = _daily()
    w_gold = feat.build(d, "iau")
    w_silver = feat.build(d, "slv")
    assert w_gold.attrs["metal"] == "gold"
    assert w_gold["mm_net_pct_oi"].iloc[-1] == pytest.approx(d["mm_net_pct_oi_gold"].iloc[-1])
    assert w_silver["mm_net_pct_oi"].iloc[-1] == pytest.approx(d["mm_net_pct_oi"].iloc[-1])
    assert w_gold["gold_ret_13w"].isna().all() and w_silver["gold_ret_13w"].notna().any()


def test_metal_survives_into_context_and_setups_respect_it():
    d = _daily()
    gold_ctx = engine.AnalogContext.from_daily(d, "gld")
    assert gold_ctx.weekly.attrs["metal"] == "gold"
    keys = set(setups.scan(gold_ctx)["key"])
    assert "gsr_high_turning" not in keys and "crowded_short" in keys
    assert "gsr_high_turning" in set(setups.scan(engine.AnalogContext.from_daily(d, "slv"))["key"])


def test_valuation_per_metal_and_in_etf_units():
    d = _daily()
    fv_gold = valuation.fair_value(d, "gold")
    assert fv_gold.attrs["drivers"] == valuation.DRIVERS["gold"]
    fv_gld = valuation.fair_value(d, "gld")
    common = fv_gld.index.intersection(fv_gold.index)
    # Same residual, price expressed in GLD shares (0.1 oz) instead of $/oz
    np.testing.assert_allclose(fv_gld.loc[common, "z"], fv_gold.loc[common, "z"])
    np.testing.assert_allclose(fv_gld.loc[common, "price"], fv_gold.loc[common, "price"] * 0.1, rtol=1e-9)
    np.testing.assert_allclose(fv_gld.loc[common, "fair_value"], fv_gold.loc[common, "fair_value"] * 0.1, rtol=1e-9)


@pytest.mark.parametrize("key,etf,fut,opt", [("slv", "SLV", "SI", "SLV"), ("iau", "IAU", "GC", "GLD"),
                                             ("gold", "GLD", "GC", "GLD")])
def test_vehicles_follow_instrument(key, etf, fut, opt):
    long_rich, _ = trade.suggest_instrument("bullish", 0.40, 0.30, None, key)
    assert long_rich.startswith(f"Long {etf}") and f"{fut} futures" in long_rich
    cheap, _ = trade.suggest_instrument("bullish", 0.20, 0.30, None, key)
    assert cheap.startswith(f"{opt} call spread")


def test_gold_scorecard_skips_silver_curve():
    curve = pd.DataFrame({"front": [50.0], "next": [49.0], "backwardation": [True], "implied_lease_pct": [8.0]})
    card = trade.build_scorecard(curve=curve, metal="gold")
    assert next(s for s in card.scores if s.lens == "curve").score == 0
    assert next(s for s in trade.build_scorecard(curve=curve).scores if s.lens == "curve").score == 2


def test_weekly_table_leads_with_instrument_and_its_positioning():
    d = _daily()[-300:]
    t_gld = dd.weekly_table(d, "gld")
    assert t_gld.index[0] == "GLD ($/share)"
    assert "Gold managed money net (% OI)" in t_gld.index and "Managed money net (% OI)" not in t_gld.index
    assert dd.weekly_table(d, "silver").index[0] == "Silver ($/oz)"
