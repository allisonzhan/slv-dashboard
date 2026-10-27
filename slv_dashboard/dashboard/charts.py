"""Plotly chart builders with a fixed, validated palette.

Rules the builders follow: one y-axis per chart (different scales become
small multiples, never a second axis); single-series charts use slot 1;
2px lines; hairline grid; unified crosshair hover. Series colors were
checked with the dataviz palette validator in both modes.
"""

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


@dataclass(frozen=True)
class Theme:
    series: tuple[str, ...]
    text_primary: str
    text_secondary: str
    muted: str
    grid: str
    baseline: str
    band: str


LIGHT = Theme(
    series=("#2a78d6", "#eb6834"),
    text_primary="#0b0b0b", text_secondary="#52514e", muted="#898781",
    grid="#e1e0d9", baseline="#c3c2b7", band="rgba(42,120,214,0.08)",
)
DARK = Theme(
    series=("#3987e5", "#d95926"),
    text_primary="#f0efec", text_secondary="#c3c2b7", muted="#898781",
    grid="#2c2c2a", baseline="#383835", band="rgba(57,135,229,0.12)",
)

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def theme_for(mode: str | None) -> Theme:
    return DARK if mode == "dark" else LIGHT


def _layout(fig: go.Figure, t: Theme, height: int, y_title: str = "", y_format: str = "") -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=56 if y_title else 8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=t.text_secondary, size=12),
        hovermode="x unified",
        hoverlabel=dict(font=dict(family=FONT)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(color=t.text_secondary)),
        showlegend=len(fig.data) > 1,
    )
    fig.update_xaxes(showgrid=False, linecolor=t.baseline, tickfont=dict(color=t.muted),
                     showspikes=True, spikemode="across", spikethickness=1, spikecolor=t.muted, spikedash="solid")
    fig.update_yaxes(gridcolor=t.grid, gridwidth=1, zeroline=False, tickfont=dict(color=t.muted),
                     title=dict(text=y_title, font=dict(color=t.muted, size=11), standoff=8),
                     tickformat=y_format, automargin=True)
    return fig


def line(series: dict[str, pd.Series], t: Theme, *, y_title: str = "", y_format: str = "",
         hover_format: str = ",.2f", height: int = 260, ref: float | None = None, ref_label: str = "") -> go.Figure:
    """Line chart; series keys become legend names, colored by fixed slot order."""
    fig = go.Figure()
    for i, (name, s) in enumerate(series.items()):
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines",
                                 line=dict(color=t.series[i], width=2),
                                 hovertemplate=f"%{{y:{hover_format}}}<extra>{name}</extra>"))
    if ref is not None:
        fig.add_hline(y=ref, line=dict(color=t.baseline, width=1),
                      annotation=dict(text=ref_label, font=dict(color=t.muted, size=11)),
                      annotation_position="top left")
    return _layout(fig, t, height, y_title, y_format)


def small_multiples(panels: dict[str, pd.Series], t: Theme, *, refs: dict[str, float] | None = None,
                    ref_label: str = "", height: int = 220, hover_format: str = ".2f") -> go.Figure:
    """One mini line chart per series, each on its own y-scale.

    The reference value goes in the panel title rather than an in-plot label,
    which would collide with the tick labels at narrow widths.
    """
    refs = refs or {}
    titles = [f"{n}  ·  {ref_label} {refs[n]:{hover_format}}" if n in refs else n for n in panels]
    fig = make_subplots(rows=1, cols=len(panels), subplot_titles=titles, horizontal_spacing=0.08)
    for i, (name, s) in enumerate(panels.items(), start=1):
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines",
                                 line=dict(color=t.series[0], width=2),
                                 hovertemplate=f"%{{y:{hover_format}}}<extra>{name}</extra>"), row=1, col=i)
        if name in refs:
            fig.add_hline(y=refs[name], line=dict(color=t.baseline, width=1), row=1, col=i)
        fig.add_hline(y=0, line=dict(color=t.grid, width=1), row=1, col=i)
    _layout(fig, t, height)
    fig.update_layout(showlegend=False, hovermode="x", margin=dict(t=28))
    fig.update_annotations(font=dict(color=t.text_secondary, size=12))
    return fig


def percentile_with_bands(s: pd.Series, t: Theme, *, height: int = 240) -> go.Figure:
    """Copper-share percentile with the monetary / industrial tercile bands labelled."""
    fig = line({"Copper share percentile": s * 100}, t, y_title="percentile", hover_format=".0f", height=height)
    for lo, hi, label in ((0, 100 / 3, "monetary"), (200 / 3, 100, "industrial")):
        fig.add_hrect(y0=lo, y1=hi, fillcolor=t.band, line_width=0, layer="below",
                      annotation=dict(text=label, font=dict(color=t.muted, size=11)),
                      annotation_position="top left" if label == "industrial" else "bottom left")
    fig.update_yaxes(range=[0, 100])
    return fig


def probability_area(s: pd.Series, t: Theme, *, name: str, height: int = 200) -> go.Figure:
    fig = go.Figure(go.Scatter(x=s.index, y=s.values * 100, name=name, mode="lines", fill="tozeroy",
                               line=dict(color=t.series[0], width=2), fillcolor=t.band,
                               hovertemplate="%{y:.0f}%<extra>" + name + "</extra>"))
    fig.add_hline(y=50, line=dict(color=t.baseline, width=1))
    _layout(fig, t, height, "probability, %")
    fig.update_yaxes(range=[0, 100])
    return fig


def fan_chart(history: pd.Series, paths: pd.DataFrame, t: Theme, *, height: int = 340,
              hover_format: str = ",.2f", y_title: str = "") -> go.Figure:
    """Recent price, then the analogs' forward paths scaled to today's level.

    ``paths`` is trading-days-ahead x analog, cumulative return. Future dates
    are business days from the last history date. Shows the 10-90 and 25-75
    percentile bands, the median path, and each analog as a hairline.
    """
    last_date, last = history.index[-1], float(history.iloc[-1])
    future = pd.bdate_range(last_date, periods=len(paths))
    levels = last * (1 + paths.to_numpy())
    fig = go.Figure()
    for j in range(levels.shape[1]):
        fig.add_trace(go.Scatter(x=future, y=levels[:, j], mode="lines", line=dict(color=t.baseline, width=1),
                                 hoverinfo="skip", showlegend=False))
    q = pd.DataFrame(levels, index=future).quantile([0.1, 0.25, 0.5, 0.75, 0.9], axis=1).T
    for lo, hi, name in ((0.1, 0.9, "10–90%"), (0.25, 0.75, "25–75%")):
        fig.add_trace(go.Scatter(x=future, y=q[hi], mode="lines", line=dict(width=0), hoverinfo="skip",
                                 showlegend=False))
        fig.add_trace(go.Scatter(x=future, y=q[lo], mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor=t.band, name=f"Analogs {name}",
                                 hovertemplate=f"%{{y:{hover_format}}}<extra>{name} low</extra>"))
    fig.add_trace(go.Scatter(x=history.index, y=history.values, mode="lines", name="Actual",
                             line=dict(color=t.text_primary, width=2),
                             hovertemplate=f"%{{y:{hover_format}}}<extra>Actual</extra>"))
    fig.add_trace(go.Scatter(x=future, y=q[0.5], mode="lines", name="Analog median",
                             line=dict(color=t.series[0], width=2, dash="dot"),
                             hovertemplate=f"%{{y:{hover_format}}}<extra>Analog median</extra>"))
    fig.add_vline(x=last_date, line=dict(color=t.baseline, width=1))
    _layout(fig, t, height, y_title)
    fig.update_layout(showlegend=True)
    return fig


def outcome_bars(outcomes: pd.DataFrame, t: Theme, *, height: int = 240) -> go.Figure:
    """Analog median forward return vs. the base rate, per horizon, with the analog IQR."""
    x = [f"{int(h)}w" for h in outcomes.index]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=outcomes["median"] * 100, name="Analogs (median)", marker_color=t.series[0],
                         error_y=dict(type="data", symmetric=False, color=t.muted, thickness=1,
                                      array=(outcomes["q75"] - outcomes["median"]) * 100,
                                      arrayminus=(outcomes["median"] - outcomes["q25"]) * 100),
                         hovertemplate="%{y:+.1f}%<extra>Analogs</extra>"))
    fig.add_trace(go.Bar(x=x, y=outcomes["base_median"] * 100, name="Base rate (median)",
                         marker_color=t.baseline, hovertemplate="%{y:+.1f}%<extra>Base rate</extra>"))
    fig.add_hline(y=0, line=dict(color=t.baseline, width=1))
    _layout(fig, t, height, "forward return, %")
    fig.update_layout(barmode="group", bargap=0.35, hovermode="x unified", showlegend=True)
    return fig


def technical_chart(tech: pd.DataFrame, t: Theme, *, height: int = 420, hover_format: str = ",.2f") -> go.Figure:
    """Price with 50/200-day MAs and Bollinger bands, RSI underneath."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    fig.add_trace(go.Scatter(x=tech.index, y=tech["bb_upper"], mode="lines", line=dict(width=0),
                             hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=tech.index, y=tech["bb_lower"], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor=t.band, name="Bollinger (20, 2σ)", hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=tech.index, y=tech["price"], mode="lines", name="Price",
                             line=dict(color=t.text_primary, width=2),
                             hovertemplate=f"%{{y:{hover_format}}}<extra>Price</extra>"), row=1, col=1)
    for col, name, color in (("sma50", "50d MA", t.series[0]), ("sma200", "200d MA", t.series[1])):
        fig.add_trace(go.Scatter(x=tech.index, y=tech[col], mode="lines", name=name, line=dict(color=color, width=1.5),
                                 hovertemplate=f"%{{y:{hover_format}}}<extra>{name}</extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=tech.index, y=tech["rsi14"], mode="lines", name="RSI(14)",
                             line=dict(color=t.series[0], width=1.5), showlegend=False,
                             hovertemplate="%{y:.0f}<extra>RSI</extra>"), row=2, col=1)
    for lvl in (30, 70):
        fig.add_hline(y=lvl, line=dict(color=t.baseline, width=1, dash="dot"), row=2, col=1)
    _layout(fig, t, height)
    fig.update_layout(showlegend=True)
    fig.update_yaxes(range=[0, 100], row=2, col=1, title=dict(text="RSI"))
    return fig


def fair_value_chart(fv: pd.DataFrame, t: Theme, *, name: str = "Silver", y_title: str = "$/oz",
                     height: int = 300) -> go.Figure:
    """Price vs. driver fair value, with the ±1σ residual band."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fv.index, y=fv["band_hi"], mode="lines", line=dict(width=0), hoverinfo="skip",
                             showlegend=False))
    fig.add_trace(go.Scatter(x=fv.index, y=fv["band_lo"], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor=t.band, name="Fair value ±1σ", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fv.index, y=fv["fair_value"], mode="lines", name="Driver fair value",
                             line=dict(color=t.series[1], width=2, dash="dot"),
                             hovertemplate="%{y:,.2f}<extra>Fair value</extra>"))
    fig.add_trace(go.Scatter(x=fv.index, y=fv["price"], mode="lines", name=name,
                             line=dict(color=t.series[0], width=2),
                             hovertemplate=f"%{{y:,.2f}}<extra>{name}</extra>"))
    _layout(fig, t, height, y_title)
    fig.update_layout(showlegend=True)
    return fig


def ratio_bands(b: pd.DataFrame, t: Theme, *, height: int = 260) -> go.Figure:
    """Gold/silver ratio inside its rolling 10th-90th percentile band."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=b.index, y=b["p90"], mode="lines", line=dict(width=0), hoverinfo="skip",
                             showlegend=False))
    fig.add_trace(go.Scatter(x=b.index, y=b["p10"], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor=t.band, name="3y 10th–90th pct", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=b.index, y=b["p50"], mode="lines", name="3y median",
                             line=dict(color=t.baseline, width=1, dash="dot"),
                             hovertemplate="%{y:.1f}<extra>3y median</extra>"))
    fig.add_trace(go.Scatter(x=b.index, y=b["gsr"], mode="lines", name="Gold/silver ratio",
                             line=dict(color=t.series[0], width=2), hovertemplate="%{y:.1f}<extra>Ratio</extra>"))
    _layout(fig, t, height)
    fig.update_layout(showlegend=True)
    return fig


def event_paths(paths: pd.DataFrame, base: pd.Series, t: Theme, *, height: int = 300) -> go.Figure:
    """Average move around past events (median and 25-75% band) vs. the unconditional drift.

    ``paths`` is days-from-event x event, as returns from the close before the event.
    """
    q = paths.quantile([0.25, 0.5, 0.75], axis=1).T * 100
    x = paths.index
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=q[0.75], mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=x, y=q[0.25], mode="lines", line=dict(width=0), fill="tonexty", fillcolor=t.band,
                             name="Events 25–75%", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=base.index, y=base.values * 100, mode="lines", name="Base drift",
                             line=dict(color=t.baseline, width=1.5, dash="dot"),
                             hovertemplate="%{y:+.1f}%<extra>Base drift</extra>"))
    fig.add_trace(go.Scatter(x=x, y=q[0.5], mode="lines", name=f"Median of {paths.shape[1]} events",
                             line=dict(color=t.series[0], width=2), hovertemplate="%{y:+.1f}%<extra>Median</extra>"))
    fig.add_vline(x=0, line=dict(color=t.baseline, width=1))
    fig.add_hline(y=0, line=dict(color=t.grid, width=1))
    _layout(fig, t, height, "% from close before event")
    fig.update_xaxes(title=dict(text="trading days from event", font=dict(color=t.muted, size=11)))
    fig.update_layout(showlegend=True, hovermode="x unified")
    return fig


def channel_scores(scores: pd.Series, t: Theme, *, threshold: float = 1.0, height: int = 220) -> go.Figure:
    """Current score per shock channel, strongest at the top; the dotted line is the labelling threshold."""
    s = scores.dropna().sort_values()
    colors = [t.series[0] if v >= threshold else t.baseline for v in s.values]
    fig = go.Figure(go.Bar(x=s.values, y=[i.replace("_", " ") for i in s.index], orientation="h",
                           marker_color=colors, hovertemplate="%{x:+.2f}<extra>%{y}</extra>"))
    fig.add_vline(x=threshold, line=dict(color=t.muted, width=1, dash="dot"))
    fig.add_vline(x=0, line=dict(color=t.baseline, width=1))
    _layout(fig, t, height)
    fig.update_layout(showlegend=False, hovermode="closest", margin=dict(l=8, r=8, t=8, b=8))
    fig.update_xaxes(showspikes=False, title=dict(text="score (scaled 4-week moves)", font=dict(color=t.muted, size=11)))
    fig.update_yaxes(showspikes=False)
    return fig