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
