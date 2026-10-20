# SLV Dashboard

Silver fundamentals dashboard and driver model for the COINS (Commodity Investing by Students) metals division at Virginia Tech.

Two pieces share one data pipeline:

1. **Fundamentals dashboard** – price, gold/silver ratio, CFTC positioning, COMEX inventories, ETF holdings, real yields and the dollar, in one Streamlit app.
2. **Driver model** – rolling regressions of silver returns on real yields, the dollar, copper and gold, plus regime detection ("monetary" vs. "industrial" silver).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # then add your FRED API key to .env
streamlit run app.py
```

Get a free FRED API key at https://fred.stlouisfed.org/docs/api/api_key.html. Never commit `.env`.

## Data sources (v1, all free)

| Series | Source |
|---|---|
| Silver, gold, copper futures | yfinance (`SI=F`, `GC=F`, `HG=F`) |
| 10Y real yield, broad dollar index | FRED (`DFII10`, `DTWEXBGS`) |
| Positioning | CFTC Commitments of Traders |
| Registered / eligible stocks | CME daily silver stocks report |
| ETF holdings | Issuer daily holdings |
| Shanghai premium | v2 |

## Layout

```
app.py                  Streamlit entry point
slv_dashboard/
  config.py             Series definitions and settings
  data/                 Loaders (one module per source)
  models/               Regressions and regime detection
data/cache/             Local data cache (git-ignored)
notebooks/              Research notebooks
```

## Roadmap

- [x] Project skeleton
- [ ] Phase 1: data loaders and aligned dataset
- [ ] Phase 2: rolling driver regressions and regime detection
- [ ] Phase 3: dashboard panels and alerts
- [ ] Phase 4: daily refresh and hosting
