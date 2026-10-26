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

## Data sources (all free)

Loaders pull the full history. The driver models and main panels use 2010 on, and the analog engine uses all of it.

| Series | Source | History |
|---|---|---|
| Silver, gold, copper, oil futures | yfinance (`SI=F`, `GC=F`, `HG=F`, `CL=F`) | 2000 on |
| SLV, silver miners, VIX | yfinance (`SLV`, `SIL`, `^VIX`) | SLV 2006 on, SIL 2010 on |
| 10Y real yield, broad dollar, 2Y yield, breakevens, fed funds | FRED (`DFII10`, `DTWEXBGS`, `DGS2`, `T10YIE`, `DFF`) | 2003/2006 on |
| Positioning | CFTC disaggregated COT, COMEX silver | 2006 on, weekly |
| SLV ounces in trust | iShares product page | Today only; builds up with each daily refresh |
| SI futures curve (next 4 liquid contracts) | yfinance (`SIZ26.CMX` etc.) | 6-month backfill, then builds up |
| SLV option IV and skew (~30 days) | yfinance option chain, IV backed out from bid/ask | Snapshots; refresh during market hours |
| FOMC decisions, payrolls/CPI estimates | `slv_dashboard/catalysts.py` plus `data/imports/calendar.csv` | 2019–2027 |
| Registered / eligible stocks | CME daily silver stocks report | Manual import, see below |
| Shanghai premium | v2 | |

**Notes**
- COT positions are as of Tuesday but released Friday. The dataset lags them 3 days so models never see data before it was public.
- yfinance `=F` tickers are continuous front-month series, so roll dates can show small artificial jumps.
- **Implied lease rate** = fed funds minus the annualised front-to-next futures spread. When it rises, or the curve flips into backwardation, near-term metal is scarce (Oct 2025). January contracts are skipped because they trade thinly.
- **Catalysts:** FOMC dates are hard-coded from the Fed's schedule (extend yearly). Payrolls and CPI dates are estimates. Put exact dates or other events in `data/imports/calendar.csv` (`date,event`).

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

## Historical analogs

```bash
python -m slv_dashboard.analogs.report   # current analogs, setup scan, walk-forward backtest (a few minutes)
```

"Silver is here, momentum is X, positioning is Y: when did this happen before, and what happened next?"

- **State vector** (`analogs/features.py`), one row per week, built with no look-ahead. *Technical*: distance from the 50/200-day MAs, 4/13/26-week returns, RSI, Bollinger %b, drawdown from the 52-week high, vol percentile. *Macro*: 13-week change in real yields, the dollar, gold and copper, plus the gold/silver ratio z-score. *Positioning*: managed-money percentile and 4-week change. Groups can be switched off, e.g. for price-only analogs.
- **Matching** (`analogs/engine.py`) combines state distance (standardised against earlier weeks only, each group weighted equally) with path shape (correlation of the last 60 days of price). A candidate's forward window must end before today. Analogs are de-clustered (one per 8 weeks) so one episode can't fill the list.
- **Outcomes** at 1, 4, 13 and 26 weeks: hit rate, median and IQR, max adverse/favourable excursion (for stops and targets), forward realised vol (for options). Each is shown **against the base rate** over the same history, with a bootstrap p-value.
- **Targets**: silver futures (default, 2000 on), SLV, the gold/silver ratio, SLV/SIL and silver/copper, so ratio and spread trades use the same engine.
- **Setups** (`analogs/setups.py`) are named rules, such as a crowded short, the ratio above 85 and turning, or a breakout with room to run. Each comes with its historical event study and a "live now" flag.
- **Walk-forward backtest** (`analogs/backtest.py`) reruns the engine every week since 2010 using only what was known then. On 2000–2026 silver it does **not** beat the base rate on direction (4w and 13w). Read the analogs as context and risk ranges, not as a buy/sell signal, unless the backtest panel says otherwise.

## Valuation and the trade builder

- **Fair value** (`models/valuation.py`): a rolling 3-year regression of log silver on log gold, the 10Y real yield, the log dollar and log copper (weekly levels). The residual z-score is the rich/cheap read. Levels relationships drift, so treat it as "stretched vs. recent relationships", not an anchor. The gold/silver ratio is shown against its own 3-year 10th–90th percentile band.
- **Scorecard** (`models/trade.py`): six lenses (analogs, setups, valuation, positioning, macro, curve), each scored −2 to +2 with its reason. The analog lens is capped at ±1 while the walk-forward backtest shows no edge. A total of +3 or more is bullish, −3 or less bearish.
- **Trade plan**:
  - **Vehicle** depends on the view and on SLV implied vol vs. the analogs' realised vol. Cheap options mean call/put spreads; rich ones mean the metal with a stop, or selling premium. With no directional edge and an extreme gold/silver ratio, it suggests a ratio pair.
  - **Stop** is the analogs' worst-quartile adverse move; **targets** are their median and 75th-percentile favourable moves. **Size** risks a set % of the book.
  - The tab exports a **monthly pitch draft** in markdown. It is club research, not investment advice.

## Alerts

Shown under the stat tiles (`models/alerts.py`), warnings first:

| Alert | Fires when |
|---|---|
| Gold/silver ratio near historic high/low | Ratio in its top or bottom 10% since 2010 |
| Speculative positioning stretched | Managed-money net % OI is 2+ standard deviations from its 3-year mean |
| Managed money flipped | Net positioning changed sign in the latest report |
| Regime changed | Either regime view changed within the last 4 weeks |
| Silver unusually sensitive to copper | Rolling copper beta is 2x+ its full-sample value |
| Prices / COT are stale | Last price more than 4 days old, or last COT release more than ~2 weeks old |
| Futures in backwardation / lease rate elevated | Next contract below front, or implied lease rate at least 3% |
| Large SLV inflow/outflow | Ounces in trust moved at least 1% since the last reading |
| Setup live | A named setup (see Historical analogs) fired this week |
| Historical analogs lean higher/lower | 13-week analog median at least 5 pts from base, p ≤ 0.10 |

## Automation and hosting

- **CI** (`.github/workflows/tests.yml`) runs `pytest` on every PR and on pushes to main.
- **Daily data refresh** (`.github/workflows/refresh-data.yml`) runs weekdays at 23:30 UTC. It restores the last published data, pulls every source, refits the models, and pushes the CSVs plus `manifest.json` to the `data` branch. Daily data never lands on `main`. Run it by hand from the Actions tab or with `gh workflow run refresh-data`.
- **The app** reads `data/cache/` locally. If the cache is empty, or `SLV_DATA_SOURCE=published` is set, it downloads the published CSVs from the `data` branch instead.

**Hosting on Streamlit Community Cloud (free):**
1. Sign in at https://share.streamlit.io with your GitHub account.
2. Create an app: repo `allisonzhan/slv-dashboard`, branch `main`, main file `app.py`.
3. Under Advanced settings → Secrets, add `SLV_DATA_SOURCE = "published"`.
4. Deploy, and share the URL with the club.

COMEX stocks still need manual imports (CME blocks automated downloads). The SLV page may also block GitHub's servers; if the refresh log shows it failing, run the refresh locally to keep that history growing.

## Layout

```
app.py                  Streamlit entry point
slv_dashboard/
  config.py             Series definitions and settings
  refresh.py            Pull every source into the cache
  data/                 Loaders (one module per source) and dataset.py (aligned daily frame)
  models/               Regressions and regime detection
  analogs/              Historical analogs, setups and backtest
data/cache/             Local data cache (git-ignored)
data/imports/           Hand-downloaded files, e.g. CME reports (git-ignored)
notebooks/              Research notebooks
tests/                  Offline tests
```

## Roadmap

- [x] Project skeleton
- [x] Phase 1: data loaders and aligned dataset (COMEX parser waits on a real CME file to verify)
- [x] Phase 2: rolling driver regressions and regime detection
- [x] Phase 3: dashboard panels and alerts
- [x] Phase 4: CI, daily data refresh, hosting setup (deploying to Streamlit Cloud is a manual step)
- [x] Phase 5: historical analog engine, setup library, walk-forward backtest
- [x] Phase 6: dashboard reorganised into tabs (Weekly Brief, Technicals & Analogs, Macro, Supply & Flows, Positioning)
- [x] Phase 7: futures curve and implied lease rate, SLV option IV/skew, catalyst calendar, FOMC event study, new alerts
- [x] Phase 8: fair-value model, gold/silver ratio bands, scorecard, trade plan and pitch draft
