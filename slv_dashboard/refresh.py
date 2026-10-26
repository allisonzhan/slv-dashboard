"""Pull every source into data/cache/. Run: python -m slv_dashboard.refresh"""

import sys

from slv_dashboard.data import cftc, comex, curve, dataset, etf, fred, options, prices

SOURCES = [
    ("prices", prices.refresh),
    ("FRED macro", fred.refresh),
    ("CFTC COT", cftc.refresh),
    ("SLV holdings", etf.refresh),
    ("COMEX stocks (imports)", comex.refresh),
    ("SI futures curve", curve.refresh),     # after FRED: uses fed funds
    ("SLV option IV", options.refresh),
]


def main() -> int:
    failures = 0
    for label, fn in SOURCES:
        try:
            df = fn()
            if df is None or df.empty:
                print(f"  {label:<24} no data (see module docstring)")
            else:
                print(f"  {label:<24} {len(df):>6} rows, latest {df.index.max():%Y-%m-%d}")
        except Exception as exc:  # keep going so one bad source doesn't block the rest
            failures += 1
            print(f"  {label:<24} FAILED: {exc}")
    df = dataset.build()
    print(f"\nAligned dataset: {len(df)} rows x {df.shape[1]} columns, {df.index.min():%Y-%m-%d} to {df.index.max():%Y-%m-%d}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
