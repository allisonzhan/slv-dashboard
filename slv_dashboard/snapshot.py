"""Everything the dashboard knows this week, as one JSON file for the agent.

The weekly-brief agent (a Claude Code skill for now; see README "Agent")
reads data/cache/snapshot.json instead of the dashboard, so it works from the
same numbers the club sees. Run after refresh, models.report and
analogs.report:

    python -m slv_dashboard.snapshot
"""

import json
import math
from datetime import date

import numpy as np
import pandas as pd

from slv_dashboard import catalysts, instruments
from slv_dashboard.analogs import backtest, engine, setups
from slv_dashboard.config import CACHE_DIR, DEFAULT_INSTRUMENT
from slv_dashboard.dashboard import data as dd
from slv_dashboard.data import cache, news
from slv_dashboard.models import alerts, trade, valuation

PATH = CACHE_DIR / "snapshot.json"
SCHEMA_VERSION = 2   # 2: instrument-aware (headline.price instead of headline.silver)
REQUIRED_KEYS = ["schema_version", "as_of", "instrument", "headline", "what_changed", "regime", "alerts", "analogs", "backtest",
                 "setups_live", "valuation", "positioning", "curve", "options", "scorecard", "trade_plan",
                 "catalysts", "news"]


def _clean(x):
    """JSON-safe: NaN -> None, numpy -> Python, timestamps -> ISO dates."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (pd.Timestamp, date)):
        return x.isoformat()[:10]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if math.isnan(x) else round(float(x), 6)
    return x


def build(today: date | None = None, instrument: str = DEFAULT_INSTRUMENT) -> dict:
    data = dd.load()
    daily, long_daily = data.daily, data.long_daily
    through = long_daily.index.max()

    inst = instruments.get(instrument)
    px = instruments.price(long_daily, instrument)
    ctx = engine.AnalogContext.from_daily(long_daily, instrument)
    res = engine.find(ctx)
    scan = setups.scan(ctx)
    fv, gsr_b = valuation.fair_value(long_daily, instrument), valuation.gsr_bands(long_daily)
    feats = ctx.weekly.iloc[-1]
    bt_key, bts = data.backtest_for(instrument)
    verdicts = {h: backtest.verdict(backtest.score(bt)) for h, bt in bts.items()}
    opts = data.options_for(instrument)
    curve = data.curve if inst.metal == "silver" else None

    active = alerts.all_alerts(
        daily, data.rule[52]["regime"], data.markov["regime"] if data.markov is not None else None,
        data.betas[52], float(data.full_betas["copper_ret"]), 52,
        curve=curve, setup_scan=scan, analog_outcomes=res.outcomes if res is not None else None)

    card = trade.build_scorecard(outcomes=res.outcomes if res is not None else None,
                                 backtest_has_edge=verdicts.get(13, "").startswith("Useful"),
                                 scan=scan, fv=fv, features=feats, curve=curve, metal=inst.metal)
    iv = float(opts["atm_iv"].iloc[-1]) if opts is not None else None
    tp = trade.plan(card, res.outcomes if res is not None else None, float(px.iloc[-1]),
                    iv=iv, gsr_pctile=float(gsr_b["pctile"].iloc[-1]), instrument=instrument)

    analogs = None
    if res is not None:
        analogs = {
            "query_date": res.query_date,
            "n_candidates": res.n_candidates,
            "now": engine.describe(res.query_features),
            "outcomes": {int(h): row.to_dict() for h, row in res.outcomes.iterrows()},
            "matches": [{"date": d, "episode": r["episode"], "context": engine.describe(r),
                         "shape_corr": r["shape_corr"], "fwd_4w": r.get("fwd_4w"), "fwd_13w": r.get("fwd_13w"),
                         "fwd_26w": r.get("fwd_26w")} for d, r in res.matches.iterrows()],
        }

    live = scan[scan["live"] & (scan["horizon_weeks"] == 13)] if not scan.empty else scan
    cot_col = "mm_net_pct_oi" if inst.metal == "silver" else "mm_net_pct_oi_gold"
    mm = daily[cot_col].dropna() if cot_col in daily else pd.Series(dtype=float)
    mm_reports = mm[mm.ne(mm.shift())]
    rule = data.rule[52].iloc[-1]
    news_df = cache.load_table(news.NAME)

    snap = {
        "schema_version": SCHEMA_VERSION,
        "as_of": through,
        "instrument": {"key": instrument, "label": inst.label, "metal": inst.metal, "kind": inst.kind,
                       "unit": inst.unit, "options": inst.options, "backtest_from": bt_key},
        "headline": {
            "price": px.iloc[-1],
            "price_1w_change": dd.change(px, 5),
            "price_4w_change": dd.change(px, 20),
            "silver": daily["silver"].iloc[-1],
            "gold_silver_ratio": daily["gold_silver_ratio"].iloc[-1],
            "stance": card.stance,
            "score": card.total,
        },
        "what_changed": dd.weekly_table(daily, instrument).reset_index().to_dict(orient="records"),
        "regime": {
            "monetary_industrial_52w": rule["regime"], "copper_share_pctile": rule["share_pctile"],
            "volatility": data.markov["regime"].iloc[-1] if data.markov is not None else None,
            "p_stressed": data.markov["p_stressed"].iloc[-1] if data.markov is not None else None,
            "betas_52w": data.betas[52].iloc[-1].to_dict(),
            "full_sample_betas": data.full_betas.to_dict(),
        },
        "alerts": [{"level": a.level, "title": a.title, "detail": a.detail} for a in active],
        "analogs": analogs,
        "backtest": verdicts,
        "setups_live": [{"setup": r["setup"], "view": r["view"], "episodes": r["n"], "median_13w": r["median"],
                         "base_13w": r["base_median"], "hit_rate": r["hit_rate"], "p_value": r["p_value"]}
                        for _, r in live.iterrows()],
        "valuation": {
            "read": valuation.read(fv), "fair_value": fv["fair_value"].iloc[-1], "z": fv["z"].iloc[-1],
            "residual_pct": fv["residual_pct"].iloc[-1], "r2": fv["r2"].iloc[-1],
            "gsr": gsr_b["gsr"].iloc[-1], "gsr_pctile_3y": gsr_b["pctile"].iloc[-1],
            "gsr_p10": gsr_b["p10"].iloc[-1], "gsr_p50": gsr_b["p50"].iloc[-1], "gsr_p90": gsr_b["p90"].iloc[-1],
        },
        "positioning": {
            "market": f"COMEX {inst.metal}",
            "mm_net_pct_oi": mm_reports.iloc[-1] if len(mm_reports) else None,
            "change_vs_prior_report": dd.change(mm_reports, 1),
            "pctile_history": feats.get("mm_pctile"),
            "released": mm_reports.index[-1] if len(mm_reports) else None,
        },
        "curve": curve.dropna(subset=["front", "next"]).iloc[-1][
            ["front", "next", "spread", "implied_financing_pct", "implied_lease_pct", "backwardation",
             "front_contract", "next_contract"]].to_dict() if curve is not None and not curve.empty else None,
        "options": (opts.iloc[-1].to_dict() | {"as_of": opts.index[-1], "ticker": inst.options})
        if opts is not None else None,
        "scorecard": [{"lens": s.lens, "score": s.score, "reason": s.reason} for s in card.scores],
        "trade_plan": {k: v for k, v in vars(tp).items()},
        "catalysts": catalysts.upcoming(today, days=14).to_dict(orient="records"),
        "news": news.top_by_bucket(news_df) if news_df is not None and not news_df.empty else {},
    }
    return _clean(snap)


def write(snap: dict | None = None, instrument: str = DEFAULT_INSTRUMENT) -> dict:
    """Build the snapshot; only the default instrument's goes to data/cache/snapshot.json.

    Other instruments' snapshots live only in their report folder, so the
    published snapshot the agent reads stays the club's default (SLV).
    """
    snap = snap or build(instrument=instrument)
    if snap.get("instrument", {}).get("key", DEFAULT_INSTRUMENT) == DEFAULT_INSTRUMENT:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


def main() -> None:
    snap = write()
    h = snap["headline"]
    print(f"Wrote {PATH} (as of {snap['as_of']}): {snap['instrument']['key'].upper()} {h['price']:.2f}, "
          f"stance {h['stance']} ({h['score']:+d}), "
          f"{len(snap['alerts'])} alerts, {len(snap['setups_live'])} live setups")


if __name__ == "__main__":
    main()
