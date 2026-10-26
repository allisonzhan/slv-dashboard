"""Futures curve, option IV, catalysts and the new alerts (all offline)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from slv_dashboard import catalysts
from slv_dashboard.data import curve, options
from slv_dashboard.models import alerts


def test_next_contracts_skip_delivery_month_and_thin_months():
    got = curve.next_contracts(date(2026, 12, 2), n=3)
    assert [t for t, _ in got] == ["SIH27.CMX", "SIK27.CMX", "SIN27.CMX"]
    assert curve.next_contracts(date(2026, 10, 26), n=1)[0][0] == "SIZ26.CMX"


def test_expiry_is_third_last_business_day():
    assert curve.expiry(2026, 12) == date(2026, 12, 29)


def test_spread_metrics_contango_and_backwardation():
    m = curve.spread_metrics(50.0, 50.5, date(2026, 12, 29), date(2027, 3, 29), funding_pct=4.0)
    assert m["implied_financing_pct"] == pytest.approx(np.log(50.5 / 50) / (90 / 365.25) * 100)
    assert m["implied_lease_pct"] == pytest.approx(4.0 - m["implied_financing_pct"])
    assert not m["backwardation"]
    tight = curve.spread_metrics(50.0, 49.8, date(2026, 12, 29), date(2027, 3, 29), funding_pct=4.0)
    assert tight["backwardation"] and tight["implied_lease_pct"] > 4.0


@pytest.mark.parametrize("call", [True, False])
def test_implied_vol_round_trip(call):
    price = options.bs_price(50, 52, 30 / 365, 0.04, 0.35, call)
    assert options.implied_vol(price, 50, 52, 30 / 365, 0.04, call) == pytest.approx(0.35, abs=1e-4)


def test_implied_vol_rejects_prices_below_intrinsic():
    assert np.isnan(options.implied_vol(0.5, 50, 45, 30 / 365, 0.04, True))


def test_option_snapshot_from_chain():
    spot, days, r = 50.0, 30, 0.04
    strikes = np.arange(40, 61, 1.0)

    def chain(call, vol_fn):
        px = [options.bs_price(spot, k, days / 365, r, vol_fn(k), call) for k in strikes]
        return pd.DataFrame({"strike": strikes, "bid": np.array(px) * 0.99, "ask": np.array(px) * 1.01})

    smile = lambda k: 0.30 + 0.002 * (k - spot)   # calls richer: positive call-minus-put skew
    snap = options.snapshot(spot, chain(True, smile), chain(False, smile), days, r)
    assert snap["atm_iv"] == pytest.approx(0.30, abs=0.01)
    assert snap["skew_call_minus_put"] > 0.01


def test_upcoming_lists_fomc_and_estimates():
    cal = catalysts.upcoming(date(2026, 10, 26), days=14)
    assert (cal["event"].str.startswith("FOMC") & (cal["date"] == date(2026, 10, 28))).any()
    assert (cal["event"].str.contains("payrolls") & (cal["date"] == date(2026, 11, 6))).any()
    assert list(cal["date"]) == sorted(cal["date"])


def test_fomc_week_mask():
    idx = pd.DatetimeIndex(["2026-10-23", "2026-10-30", "2026-11-06"])
    assert list(catalysts.fomc_week_mask(idx)) == [False, True, False]


def test_curve_tightness_alerts():
    c = pd.DataFrame({"front": [50.0], "next": [49.9], "backwardation": [True], "implied_lease_pct": [5.0]},
                     index=[pd.Timestamp("2026-10-26")])
    assert "backwardation" in alerts.curve_tightness(c).title
    c2 = c.assign(next=50.3, backwardation=False, implied_lease_pct=-1.0)
    assert alerts.curve_tightness(c2) is None


def test_slv_flow_alert():
    idx = pd.bdate_range("2026-10-19", periods=4)
    daily = pd.DataFrame({"slv_ounces": [500e6, 500e6, 500e6, 507e6]}, index=idx)
    a = alerts.slv_flow(daily)
    assert a is not None and "inflow" in a.title


def test_analog_edge_alert_needs_size_and_significance():
    o = pd.DataFrame({"edge_median": [0.08], "median": [0.10], "base_median": [0.02], "p_value": [0.04]}, index=[13])
    assert "higher" in alerts.analog_edge(o).title
    assert alerts.analog_edge(o.assign(p_value=0.4)) is None
