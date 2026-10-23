"""Run every model, cache the outputs for the dashboard, and print a summary.

Run: python -m slv_dashboard.models.report
"""

import warnings

import pandas as pd

from slv_dashboard.config import REGRESSION_WINDOWS_WEEKS
from slv_dashboard.data import cache, dataset
from slv_dashboard.models import drivers, regimes


def run() -> dict:
    returns = drivers.weekly_returns(dataset.build())
    out = {"returns": returns}
    for spec_name, spec in (("macro", drivers.MACRO), ("with_gold", drivers.WITH_GOLD)):
        out[f"full_{spec_name}"] = drivers.full_sample(returns, spec)
        out[f"stability_{spec_name}"] = drivers.stability_test(returns, spec)
        for w in REGRESSION_WINDOWS_WEEKS:
            betas = drivers.rolling_betas(returns, w, spec)
            cache.save(f"betas_{spec_name}_{w}w", betas)
            out[f"betas_{spec_name}_{w}w"] = betas
    for w in REGRESSION_WINDOWS_WEEKS:
        rule = regimes.rule_based(returns, w)
        cache.save(f"regime_rule_{w}w", rule)
        out[f"regime_rule_{w}w"] = rule
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # statsmodels convergence chatter during search_reps
        mk = regimes.markov(returns)
    cache.save("regime_markov", mk)
    out["regime_markov"] = mk
    return out


def _print_summary(out: dict) -> None:
    r = out["returns"]
    print(f"Weekly returns: {len(r)} weeks, {r.index.min():%Y-%m-%d} to {r.index.max():%Y-%m-%d}\n")

    for spec in ("macro", "with_gold"):
        res = out[f"full_{spec}"]
        print(f"Full sample ({spec}), HAC t-stats, R^2 {res.rsquared:.2f}")
        for name in res.params.index.drop("const"):
            print(f"  {name:<16} beta {res.params[name]:>7.3f}   t {res.tvalues[name]:>6.2f}")
        st = out[f"stability_{spec}"]
        verdict = "drifted" if st["p_value"] < 0.05 else "stable"
        print(f"  CUSUM p-value {st['p_value']:.3f} ({verdict})\n")

    for w in REGRESSION_WINDOWS_WEEKS:
        b = out[f"betas_macro_{w}w"].iloc[-1]
        rule = out[f"regime_rule_{w}w"].iloc[-1]
        print(f"Latest {w}-week window (ending {out[f'betas_macro_{w}w'].index[-1]:%Y-%m-%d})")
        print("  macro betas: " + ", ".join(f"{k} {v:.2f}" for k, v in b.items()))
        print(f"  R^2 gold {rule['r2_gold']:.2f} vs copper {rule['r2_copper']:.2f}; copper share "
              f"{rule['industrial_share']:.0%} ({rule['share_pctile']:.0%} percentile) -> {rule['regime'].upper()}")
        share = out[f"regime_rule_{w}w"]["regime"].value_counts(normalize=True)
        print("  history: " + ", ".join(f"{k} {v:.0%}" for k, v in share.items()) + "\n")

    mk = out["regime_markov"]
    print(f"Markov regime now: {mk['regime'].iloc[-1].upper()} (p_stressed {mk['p_stressed'].iloc[-1]:.2f})")
    for name, d in mk.attrs["regimes"].items():
        share = (mk["regime"] == name).mean()
        print(f"  {name:<9} {share:>4.0%} of weeks  gold beta {d['gold_beta']:.2f}  copper beta {d['copper_beta']:.2f}"
              f"  vol {d['weekly_vol_pct']:.1f}%/wk  avg spell {d['expected_weeks']:.0f} wks")


def main() -> None:
    pd.set_option("display.width", 160)
    _print_summary(run())


if __name__ == "__main__":
    main()
