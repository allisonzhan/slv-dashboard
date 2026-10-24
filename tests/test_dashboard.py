"""Dashboard helpers and chart builders."""

import pandas as pd

from slv_dashboard.dashboard import charts
from slv_dashboard.dashboard import data as dd


def _series(years=6):
    idx = pd.bdate_range(end="2026-10-22", periods=252 * years)
    return pd.Series(range(len(idx)), index=idx, dtype=float)


def test_clip_trailing_range():
    s = _series()
    one = dd.clip(s, "1Y")
    assert one.index.min() >= pd.Timestamp("2025-10-22")
    assert len(dd.clip(s, "All")) == len(s)


def test_change_handles_short_series():
    assert dd.change(pd.Series([1.0, 3.0]), 1) == 2.0
    assert dd.change(pd.Series([1.0]), 5) is None


def test_theme_follows_mode():
    assert charts.theme_for("dark") is charts.DARK
    assert charts.theme_for("light") is charts.LIGHT
    assert charts.theme_for(None) is charts.LIGHT


def test_single_series_line_uses_slot_one_without_legend():
    fig = charts.line({"Silver": _series(1)}, charts.LIGHT)
    assert fig.data[0].line.color == charts.LIGHT.series[0]
    assert fig.layout.showlegend is False


def test_two_series_keep_fixed_slot_order_and_show_legend():
    s = _series(1)
    fig = charts.line({"Registered": s, "Eligible": s * 2}, charts.DARK)
    assert [tr.line.color for tr in fig.data] == list(charts.DARK.series)
    assert fig.layout.showlegend is True


def test_small_multiples_one_axis_per_panel_with_reference_in_title():
    s = _series(1)
    fig = charts.small_multiples({"Copper": s, "Dollar": -s}, charts.LIGHT,
                                 refs={"Copper": 0.46}, ref_label="full sample")
    titles = [a.text for a in fig.layout.annotations]
    assert "Copper  ·  full sample 0.46" in titles
    assert fig.data[0].yaxis != fig.data[1].yaxis  # separate scales, never a shared dual axis
