"""Compute the current analog read, setup scan and walk-forward backtest, and cache them.

Run: python -m slv_dashboard.analogs.report

The current read and setup scan are for the default instrument (SLV). The
walk-forward backtest runs for each instrument in ANALOG_BACKTEST_INSTRUMENTS
(one per metal by default); the dashboard computes current analogs for any
instrument on the fly, and reuses the same metal's backtest when an
instrument has none of its own.
"""

import pandas as pd

from slv_dashboard import events
from slv_dashboard.analogs import backtest, engine, setups
from slv_dashboard.config import ANALOG_BACKTEST_INSTRUMENTS, DEFAULT_INSTRUMENT
from slv_dashboard.data import cache, dataset

BACKTEST_HORIZONS = [4, 13]


def backtest_name(instrument: str, horizon: int) -> str:
    return f"analog_backtest_{instrument}_{horizon}w"


def run(target: str = DEFAULT_INSTRUMENT, backtest_instruments: list[str] = ANALOG_BACKTEST_INSTRUMENTS) -> dict:
    daily = dataset.build(start=None)
    ctx = engine.AnalogContext.from_daily(daily, target)
    res = engine.find(ctx)
    out = {"ctx": ctx, "result": res, "target": target}
    if res is not None:
        m = res.matches.copy()
        m["context"] = [engine.describe(r) for _, r in m.iterrows()]
        cache.save("analogs_current", m)
        cache.save_table("analog_outcomes", res.outcomes)
        paths = res.paths.copy()
        paths.columns = [f"{d:%Y-%m-%d}" for d in paths.columns]
        cache.save_table("analog_paths", paths)
    scan = setups.scan(ctx, setups.SETUPS + events.event_setups(events.catalogue(daily)))
    cache.save_table("setups", scan)
    out["setups"] = scan

    scores = {}
    for key in backtest_instruments:
        bt_ctx = ctx if key == target else engine.AnalogContext.from_daily(daily, key)
        for h in BACKTEST_HORIZONS:
            bt = backtest.run(bt_ctx, h)
            cache.save(backtest_name(key, h), bt)
            scores[(key, h)] = backtest.score(bt)
    out["backtest"] = scores
    return out


def print_summary(out: dict) -> None:
    res = out["result"]
    if res is None:
        print("Analogs: not enough history")
        return
    print(f"Analogs for {out['target']}, week of {res.query_date:%Y-%m-%d} ({res.n_candidates} candidate weeks, "
          f"{len(res.features_used)} features)")
    for d, r in res.matches.head(10).iterrows():
        ep = f"  [{r['episode']}]" if r["episode"] else ""
        print(f"  {d:%Y-%m-%d}  score {r['score']:.2f}  shape {r['shape_corr']:+.2f}  "
              f"13w fwd {r.get('fwd_13w', float('nan')):+.1%}{ep}")
    print("\n  horizon  hit   median   base   edge    p")
    for h, o in res.outcomes.iterrows():
        print(f"  {int(h):>4}w   {o['hit_rate']:.0%}  {o['median']:+6.1%}  {o['base_median']:+6.1%}  "
              f"{o['edge_median']:+6.1%}  {o['p_value']:.2f}")
    live = out["setups"]
    live = live[live["live"]]["setup"].unique() if not live.empty else []
    print("\nLive setups: " + (", ".join(live) if len(live) else "none"))
    for (key, h), sc in out["backtest"].items():
        print(f"\nBacktest {key} {h}w ({sc['n']} weeks): {backtest.verdict(sc)}")
        if sc["n"]:
            print(f"  direction accuracy {sc['direction_accuracy']:.0%} vs base {sc['base_direction_accuracy']:.0%}"
                  f" / always-up {sc['always_up_accuracy']:.0%}")


def main() -> None:
    pd.set_option("display.width", 160)
    print_summary(run())


if __name__ == "__main__":
    main()
