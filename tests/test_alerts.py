"""Alert rules on small synthetic inputs."""

import numpy as np
import pandas as pd

from slv_dashboard.models import alerts


def _daily(ratio_last: float, n=500):
    idx = pd.bdate_range(end="2026-10-22", periods=n)
    ratio = np.full(n, 75.0) + np.sin(np.arange(n) / 20) * 5
    ratio[-1] = ratio_last
    return pd.DataFrame({"gold_silver_ratio": ratio, "silver": 50.0}, index=idx)


def _with_positioning(df: pd.DataFrame, weekly_values: list[float]) -> pd.DataFrame:
    fridays = df.index[df.index.dayofweek == 4][-len(weekly_values):]
    s = pd.Series(weekly_values, index=fridays).reindex(df.index).ffill()
    return df.assign(mm_net_pct_oi=s)


def test_ratio_extreme_high_and_normal():
    assert alerts.ratio_extreme(_daily(95.0)).title.startswith("Gold/silver ratio near historic high")
    assert alerts.ratio_extreme(_daily(75.0)) is None


def test_positioning_extreme_flags_crowded_long():
    vals = list(np.random.default_rng(0).normal(5, 2, 99)) + [20.0]
    a = alerts.positioning_extreme(_with_positioning(_daily(75.0), vals))
    assert a is not None and "long" in a.title


def test_positioning_flip_detects_sign_change():
    vals = list(np.linspace(3, 1, 20)) + [-1.5]
    a = alerts.positioning_flip(_with_positioning(_daily(75.0), vals))
    assert a is not None and "net short" in a.title


def test_regime_change_recent_only():
    idx = pd.date_range("2026-01-02", periods=20, freq="W-FRI")
    steady = pd.Series(["calm"] * 20, index=idx)
    assert alerts.regime_change(steady, "Volatility") is None
    changed = pd.Series(["calm"] * 18 + ["stressed"] * 2, index=idx)
    a = alerts.regime_change(changed, "Volatility")
    assert a is not None and a.title.endswith("stressed")


def test_copper_beta_stretched():
    betas = pd.DataFrame({"copper_ret": [0.4, 1.2]})
    assert alerts.copper_beta_stretched(betas, 0.46, 52) is not None
    assert alerts.copper_beta_stretched(betas.iloc[:1], 0.46, 52) is None


def test_stale_prices_and_warning_order():
    df = _daily(95.0)
    out = alerts.all_alerts(df, pd.Series(["mixed"] * 5), None, pd.DataFrame({"copper_ret": [0.1]}),
                            0.46, 52, today=df.index[-1] + pd.Timedelta(days=10))
    titles = [a.title for a in out]
    assert "Prices are stale" in titles
    assert all(a.level == alerts.WARN for a in out[:2])
