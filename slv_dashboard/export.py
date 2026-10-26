"""Weekly deliverable: a one-page brief plus a chart pack, under reports/YYYY-MM-DD/.

    python -m slv_dashboard.export            # snapshot -> brief.md, brief.html, charts/*.png
    python -m slv_dashboard.export --html     # re-render brief.html after editing brief.md

brief.md is filled from snapshot.json. Sections that need judgment (the
bottom line, the news that matters, talking points) sit between
<!-- AGENT:name --> and <!-- /AGENT --> markers. They hold a numbers-only
fallback until the weekly-brief agent (or you) rewrites them. Then run
--html again. Open brief.html in a browser and print it to PDF.

PNG export needs kaleido and a local Chrome. If either is missing, charts
are skipped and the brief still renders.
"""

import argparse
import json
import re
from pathlib import Path

import markdown
import pandas as pd

from slv_dashboard import snapshot as snap_mod
from slv_dashboard.analogs import engine
from slv_dashboard.analogs import features as feat
from slv_dashboard.config import ROOT
from slv_dashboard.dashboard import charts
from slv_dashboard.dashboard import data as dd
from slv_dashboard.models import trade, valuation

REPORTS_DIR = ROOT / "reports"
AGENT_RE = re.compile(r"<!-- AGENT:(\w+) -->(.*?)<!-- /AGENT -->", re.S)


def pct(v, signed=True):
    if v is None:
        return "–"
    return f"{v:+.1%}" if signed else f"{v:.0%}"


def _agent(name: str, fallback: str) -> str:
    return f"<!-- AGENT:{name} -->\n{fallback.strip()}\n<!-- /AGENT -->"


def render_markdown(s: dict) -> str:
    """The one-page brief from a snapshot dict."""
    h, a, v, pos = s["headline"], s.get("analogs"), s["valuation"], s["positioning"]
    o13 = (a or {}).get("outcomes", {}).get("13") or (a or {}).get("outcomes", {}).get(13)
    o4 = (a or {}).get("outcomes", {}).get("4") or (a or {}).get("outcomes", {}).get(4)
    as_of = pd.Timestamp(s["as_of"])

    bottom = (f"Silver {h['silver']:.2f} ({h['silver_1w_change']:+.2f} on the week). Scorecard reads "
              f"**{h['stance']}** ({h['score']:+d} of ±12). _Replace with the 2-sentence view and why._")
    L = [f"# Silver weekly brief: week of {as_of:%b %d, %Y}", "", "## Bottom line", _agent("bottom_line", bottom), ""]

    L += ["## What changed", "| Series | Latest | 1w | 4w | Pctile |", "|---|---|---|---|---|"]
    L += [f"| {r['Series']} | {r['Latest']} | {r['1w change']} | {r['4w change']} | {r['Percentile']} |"
          for r in s["what_changed"]]
    rg = s["regime"]
    L += ["", f"Regime: **{rg['monetary_industrial_52w']}** (copper share {pct(rg['copper_share_pctile'], False)} "
              f"pctile), volatility **{rg['volatility']}** (p stressed {pct(rg['p_stressed'], False)}).", ""]

    L += ["## Historical analogs"]
    if a:
        L += [f"Now: {a['now']}."]
        for label, o in (("4 weeks", o4), ("13 weeks", o13)):
            if o:
                L.append(f"- **{label}:** analogs {pct(o['median'])} median, up {pct(o['hit_rate'], False)} vs. base "
                         f"{pct(o['base_median'])} / {pct(o['base_hit_rate'], False)} (p {o['p_value']:.2f}); "
                         f"typical drawdown {pct(o['mae_median'])}, worst quartile {pct(o['mae_q25'])}")
        top = a["matches"][:3]
        L.append("- Closest: " + "; ".join(f"{m['date'][:7]}{' (' + m['episode'] + ')' if m['episode'] else ''} "
                                            f"→ 13w {pct(m['fwd_13w'])}" for m in top))
    for hz, verdict in s["backtest"].items():
        L.append(f"- Track record ({hz}w): {verdict}")
    if s["setups_live"]:
        L += ["", "**Live setups:** " + "; ".join(
            f"{x['setup']} ({x['view']}, {x['episodes']:.0f} episodes, 13w median {pct(x['median_13w'])} vs. "
            f"{pct(x['base_13w'])})" for x in s["setups_live"])]
    L.append("")

    L += ["## Positioning, flows and valuation"]
    if pos["mm_net_pct_oi"] is not None:
        L.append(f"- Managed money net {pos['mm_net_pct_oi']:.1f}% of OI ({pos['change_vs_prior_report']:+.1f} pts), "
                 f"{pct(pos['pctile_history'], False)} percentile of history")
    if s["curve"]:
        c = s["curve"]
        L.append(f"- Curve {c['front_contract'][:5]}→{c['next_contract'][:5]} spread {c['spread']:+.3f} "
                 f"({'backwardation' if c['backwardation'] else 'contango'}), implied lease {c['implied_lease_pct']:+.2f}%")
    if s["options"]:
        op = s["options"]
        L.append(f"- SLV ATM IV {pct(op['atm_iv'], False)} ({op['days']:.0f}d), skew call−put {pct(op['skew_call_minus_put'])}")
    L.append(f"- Valuation: {v['read']} Gold/silver ratio {v['gsr']:.1f}, {pct(v['gsr_pctile_3y'], False)} of its 3y range")
    L.append("")

    news_lines = []
    for bucket, items in (s.get("news") or {}).items():
        if items:
            news_lines.append(f"- **{bucket.replace('_', ' ')}:** {items[0]['title']} ({items[0]['source']})")
    L += ["## News that matters", _agent("news", "\n".join(news_lines) or "_No headlines cached._"), ""]

    L += ["## Scorecard", "| Lens | Score | Why |", "|---|---|---|"]
    L += [f"| {x['lens'].title()} | {x['score']:+d} | {x['reason']} |" for x in s["scorecard"]]
    tp = s["trade_plan"]
    L += ["", f"**Trade idea:** {tp['instrument']}. {tp['rationale']}"]
    if tp["stance"] != "neutral" and tp["stop"] is not None:
        L.append(f"Entry {tp['entry']:.2f}, stop {tp['stop']:.2f}, targets "
                 + " / ".join(f"{x:.2f}" for x in tp["targets"]) + f" ({tp['horizon_weeks']}w).")
    L.append("")

    L += ["## Catalysts (next 2 weeks)"]
    L += [f"- {pd.Timestamp(c['date']):%a %b %d}: {c['event']}" for c in s["catalysts"]] or ["- None scheduled"]
    L.append("")
    L += ["## Talking points", _agent("talking_points", "- _Three bullets for the meeting._"), ""]
    L += ["## Alerts"] + ([f"- **{x['title']}.** {x['detail']}" for x in s["alerts"]] or ["- None"])
    L += ["", "_COINS silver division · club research, not investment advice._"]
    return "\n".join(L)


def render_pitch(s: dict) -> str:
    """Monthly pitch skeleton from the snapshot's scorecard and trade plan (thesis left for the analyst/agent)."""
    card = trade.Scorecard([trade.Score(**x) for x in s["scorecard"]])
    tp = trade.TradePlan(**s["trade_plan"])
    a = s.get("analogs") or {}
    o13 = a.get("outcomes", {}).get("13")
    lines = []
    if o13:
        lines.append(f"{len(a['matches'])} closest past setups: 13w median {pct(o13['median'])} vs. base "
                     f"{pct(o13['base_median'])}, up {pct(o13['hit_rate'], False)} (p {o13['p_value']:.2f})")
        lines += [f"{m['date'][:7]}{' (' + m['episode'] + ')' if m['episode'] else ''}: 13w {pct(m['fwd_13w'])}"
                  for m in a["matches"][:5]]
    cal = pd.DataFrame(s["catalysts"])
    if not cal.empty:
        cal["date"] = pd.to_datetime(cal["date"])
    return trade.pitch_markdown(card, tp, as_of=pd.Timestamp(s["as_of"]), analog_lines=lines, catalysts=cal,
                                backtest_verdict=s["backtest"].get("13", ""))


CSS = """
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:860px;margin:24px auto;padding:0 16px;
color:#0b0b0b;font-size:13px;line-height:1.45}
h1{font-size:20px;margin:0 0 8px}h2{font-size:15px;margin:16px 0 6px;border-bottom:1px solid #e1e0d9;padding-bottom:2px}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{border-bottom:1px solid #e1e0d9;padding:3px 6px;
text-align:left}th{color:#52514e;font-weight:600}ul{margin:4px 0;padding-left:18px}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:8px;page-break-before:always}.charts img{width:100%}
.charts figcaption{font-size:11px;color:#52514e}
@media print{body{margin:0}}
"""


def render_html(md_text: str, chart_files: list[Path]) -> str:
    body = markdown.markdown(AGENT_RE.sub(lambda m: m.group(2), md_text), extensions=["tables"])
    figs = "".join(f'<figure><img src="charts/{p.name}"><figcaption>{p.stem.replace("_", " ")}</figcaption></figure>'
                   for p in chart_files)
    pack = f'<h2>Chart pack</h2><div class="charts">{figs}</div>' if figs else ""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Silver weekly brief</title>" \
           f"<style>{CSS}</style></head><body>{body}{pack}</body></html>"


def chart_pack(out_dir: Path) -> list[Path]:
    """Render the meeting charts to PNG (light theme, white background)."""
    t = charts.LIGHT
    data = dd.load()
    daily, long_daily = data.daily, data.long_daily
    ctx = engine.AnalogContext.from_daily(long_daily, "silver")
    res = engine.find(ctx)
    fv, gsr_b = valuation.fair_value(long_daily), valuation.gsr_bands(long_daily)
    two_y = lambda x: dd.clip(x, "3Y")   # noqa: E731

    figs = {
        "1_silver_technicals": charts.technical_chart(two_y(feat.technicals(feat.target_series(long_daily, "silver"))), t),
        "2_analog_fan_13w": charts.fan_chart(feat.target_series(long_daily, "silver").iloc[-120:],
                                             res.paths.iloc[:66], t) if res is not None else None,
        "3_analog_outcomes": charts.outcome_bars(res.outcomes, t) if res is not None else None,
        "4_fair_value": charts.fair_value_chart(two_y(fv), t),
        "5_gold_silver_ratio": charts.ratio_bands(two_y(gsr_b), t),
        "6_cot_positioning": charts.line({"Managed money net, % OI": two_y(daily["mm_net_pct_oi"].dropna())}, t,
                                         y_title="% of OI", hover_format=".1f", ref=0),
        "7_real_yield": charts.line({"10Y real yield": two_y(daily["real_yield_10y"].dropna())}, t, y_title="%"),
        "8_dollar": charts.line({"Broad dollar": two_y(daily["dollar_broad"].dropna())}, t, y_title="index"),
    }
    if data.curve is not None and data.curve["implied_lease_pct"].notna().any():
        figs["9_implied_lease"] = charts.line({"Implied lease rate": data.curve["implied_lease_pct"].dropna()}, t,
                                              y_title="%", ref=0)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, fig in figs.items():
        if fig is None:
            continue
        fig.update_layout(paper_bgcolor="white", plot_bgcolor="white", width=800, height=420,
                          margin=dict(l=56, r=16, t=64, b=32), title=dict(text=name[2:].replace("_", " "), x=0.01, y=0.98),
                          legend=dict(y=1.02))
        path = out_dir / f"{name}.png"
        try:
            fig.write_image(path, scale=2)
        except Exception as exc:  # kaleido/Chrome missing: the brief still works without the pack
            print(f"  chart pack skipped ({exc.__class__.__name__}: {exc})")
            return written
        written.append(path)
    return written


def export(html_only: bool = False, out: Path | None = None) -> Path:
    if html_only:
        out = out or max(REPORTS_DIR.glob("20*"), default=None)
        if out is None:
            raise SystemExit("No report yet; run without --html first")
        md_text = (out / "brief.md").read_text(encoding="utf-8")
    else:
        s = snap_mod.write()
        out = out or REPORTS_DIR / s["as_of"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "snapshot.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
        md_text = render_markdown(s)
        (out / "brief.md").write_text(md_text, encoding="utf-8")
        (out / "pitch.md").write_text(render_pitch(s), encoding="utf-8")
        chart_pack(out / "charts")
    pngs = sorted((out / "charts").glob("*.png")) if (out / "charts").exists() else []
    (out / "brief.html").write_text(render_html(md_text, pngs), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", action="store_true", help="only re-render brief.html from the latest brief.md")
    args = ap.parse_args()
    out = export(html_only=args.html)
    print(f"Brief written to {out}")


if __name__ == "__main__":
    main()
