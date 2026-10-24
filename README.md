# SLV Dashboard

Silver fundamentals dashboard and driver model for the COINS (Commodity Investing by Students) metals division at Virginia Tech.

Two pieces share one data pipeline:

1. **Fundamentals dashboard** – price, gold/silver ratio, CFTC positioning, COMEX inventories, ETF holdings, real yields and the dollar, in one Streamlit app.
2. **Driver model** – rolling regressions of silver returns on real yields, the dollar, copper and gold, plus regime detection ("monetary" vs. "industrial" silver).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
python -m slv_dashboard.refresh   # pull all sources into data/cache/
streamlit run app.py
pytest                            # offline parser tests
```

A FRED API key is optional (the keyless CSV endpoint is used otherwise). If you want one, copy `.env.example` to `.env` and add it. Never commit `.env`.

## Data sources (v1, all free)

| Series | Source | History |
|---|---|---|
| Silver, gold, copper futures | yfinance (`SI=F`, `GC=F`, `HG=F`) | 2010 on |
| 10Y real yield, broad dollar index | FRED (`DFII10`, `DTWEXBGS`) | 2010 on |
| Positioning | CFTC disaggregated COT, COMEX silver | 2010 on, weekly |
| SLV ounces in trust | iShares product page | Today only; builds up with each daily refresh |
| Registered / eligible stocks | CME daily silver stocks report | Manual import, see below |
| Shanghai premium | v2 | |

**Notes**
- COT positions are as of Tuesday but released Friday. The dataset lags them 3 days so models never see data before it was public.
- yfinance `=F` tickers are continuous front-month series, so roll dates can show small artificial jumps.

**COMEX stocks (manual import).** CME blocks automated downloads. Save
https://www.cmegroup.com/delivery_reports/Silver_stocks.xls from your browser into `data/imports/`
(any name starting with `Silver_stocks`, e.g. `Silver_stocks_2026-10-20.xls`) and run the refresh.
Each file is one day.

## Driver model

```bash
python -m slv_dashboard.models.report   # fits everything, caches outputs, prints a summary
```

- **Weekly returns.** COMEX settles at 1:30pm ET while FRED's yields and dollar are stamped at other times of day, so daily betas would be biased toward zero. A week still in progress is dropped.
- **Two specifications.** `MACRO` (real-yield change, dollar, copper) and `WITH_GOLD` (adds gold). Full-sample fits use Newey-West standard errors and a CUSUM stability test; rolling fits use 26- and 52-week windows.
- **Monetary vs. industrial (rule).** Copper's share of explanatory power, `r2_copper / (r2_gold + r2_copper)`, is ranked against all earlier windows (no look-ahead). Top third is industrial, bottom third monetary. Gold out-explains copper in about 90% of windows, so a raw comparison would always say monetary. Since the labels are relative, a regime lasting years drifts toward "mixed"; check `industrial_share` for the level.
- **Calm vs. stressed (Markov).** A two-regime Markov-switching regression on gold and copper. On 2010–2026 data the regimes separate by volatility (stressed weeks have higher gold *and* copper betas), so they are labelled by volatility, not as monetary/industrial. Returns are scaled to percent and the extreme 0.5% of weeks clipped, otherwise the fit collapses onto single crash weeks.

## Layout

```
app.py                  Streamlit entry point
slv_dashboard/
  config.py             Series definitions and settings
  refresh.py            Pull every source into the cache
  data/                 Loaders (one module per source) and dataset.py (aligned daily frame)
  models/               Regressions and regime detection
data/cache/             Local data cache (git-ignored)
data/imports/           Hand-downloaded files, e.g. CME reports (git-ignored)
notebooks/              Research notebooks
tests/                  Offline tests
```

## Roadmap

- [x] Project skeleton
- [x] Phase 1: data loaders and aligned dataset (COMEX parser waits on a real CME file to verify)
- [x] Phase 2: rolling driver regressions and regime detection
- [x] Phase 3: dashboard panels (alerts still to do)
- [ ] Phase 4: daily refresh and hosting
